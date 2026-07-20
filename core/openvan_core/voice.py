"""Voice pipeline — offline-first STT/TTS behind one seam.

Voice is an *enhancement*, never a requirement: dictated text goes through the same
safety-checked text-intent path as typing (Rule 2), and everything works with no
mic and no model at all (Rule 3). This module is the Core-side seam:

* **Engines** implement :class:`SttEngine` / :class:`TtsEngine`. The real ones —
  faster-whisper (STT) and piper (TTS) — are an *optional extra*
  (``pip install -e ".[voice]"``) so the edge runtime stays small.
* **Sim engines** are the dev stand-in (Rule 1): ``SimStt`` decodes a
  ``SIMVOICE:<text>`` payload into its transcript — the bench "injects the raw
  signal", here a canned utterance — and ``SimTts`` renders a small deterministic
  WAV chime, so the whole pipeline is exercisable and testable with no ML
  dependencies and no mic.
* :class:`VoiceService` resolves engines from config: ``auto`` prefers a real
  engine when its library is installed, falls back to sim in simulate mode, else
  reports unavailable. The front-end feature-detects via ``GET /api/voice`` and
  keeps using the browser speech APIs when Core has nothing better.

> The whisper/piper wrappers are **validated end-to-end** (dev machine): piper
> speaks a phrase → whisper transcribes it back verbatim, over the HTTP API.
> Still to do on the real edge box: profile CPU/latency and pick model sizes.
"""

from __future__ import annotations

import asyncio
import io
import logging
import math
import struct
import wave
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

SIM_PREFIX = b"SIMVOICE:"


class VoiceError(Exception):
    """A transcription/synthesis failure the API can report cleanly."""


class SttEngine(ABC):
    name: str = "stt"

    @abstractmethod
    async def transcribe(self, audio: bytes, content_type: str = "", language: str | None = None) -> str:
        ...


class TtsEngine(ABC):
    name: str = "tts"

    @abstractmethod
    async def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]:
        """Return (audio bytes, mime type)."""


# --- sim engines (the dev stand-in, Rule 1) ----------------------------------

class SimStt(SttEngine):
    """Decodes a canned utterance: ``SIMVOICE:<utf-8 text>`` → the text.

    This is deliberately *not* a speech model — it is the bench's way to inject
    "what was said" without a mic, exactly like SignalSliders inject sensor values.
    """

    name = "sim"

    async def transcribe(self, audio: bytes, content_type: str = "", language: str | None = None) -> str:
        if not audio.startswith(SIM_PREFIX):
            raise VoiceError(
                "sim STT only understands SIMVOICE:<text> payloads (install the "
                "'voice' extra for real speech recognition)"
            )
        return audio[len(SIM_PREFIX):].decode("utf-8", "replace").strip()


class SimTts(TtsEngine):
    """A deterministic little WAV chime — length scales with the word count.

    Not speech, but a real playable waveform, so the bench and tests exercise the
    full audio path (bytes, mime, playback) with zero dependencies.
    """

    name = "sim"

    RATE = 16000

    async def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]:
        words = max(1, min(len(text.split()), 12))
        duration = 0.12 * words  # a short chime per word, capped
        n = int(self.RATE * duration)
        frames = bytearray()
        for i in range(n):
            t = i / self.RATE
            # Two soft sines with a gentle decay — pleasant, not a buzzer.
            amp = 0.4 * math.exp(-1.5 * t)
            sample = amp * (math.sin(2 * math.pi * 660 * t) + 0.5 * math.sin(2 * math.pi * 880 * t))
            frames += struct.pack("<h", int(max(-1.0, min(1.0, sample)) * 32767))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.RATE)
            w.writeframes(bytes(frames))
        return buf.getvalue(), "audio/wav"


# --- real engines (optional extra; adapter-isolated, lazily imported) --------

class WhisperStt(SttEngine):
    """faster-whisper, running off the event loop (CPU-bound)."""

    name = "whisper"

    def __init__(self, model_size: str = "base") -> None:
        from faster_whisper import WhisperModel  # optional extra

        self._model = WhisperModel(model_size, device="cpu", compute_type="int8")

    async def transcribe(self, audio: bytes, content_type: str = "", language: str | None = None) -> str:
        def _run() -> str:
            segments, _info = self._model.transcribe(io.BytesIO(audio), language=language)
            return " ".join(s.text.strip() for s in segments).strip()

        try:
            return await asyncio.to_thread(_run)
        except Exception as exc:  # pragma: no cover - depends on real audio/model
            raise VoiceError(f"transcription failed: {exc}") from exc


class PiperTts(TtsEngine):
    """piper TTS from a local .onnx voice model."""

    name = "piper"

    def __init__(self, model_path: str) -> None:
        from piper import PiperVoice  # optional extra

        self._voice = PiperVoice.load(model_path)

    async def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]:
        def _run() -> bytes:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                # synthesize_wav sets the WAV format from the voice model itself.
                self._voice.synthesize_wav(text, w)
            return buf.getvalue()

        try:
            return await asyncio.to_thread(_run), "audio/wav"
        except Exception as exc:  # pragma: no cover - depends on a real model
            raise VoiceError(f"synthesis failed: {exc}") from exc


# --- the service --------------------------------------------------------------

def _whisper_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("faster_whisper") is not None


def _piper_available(model_path: str) -> bool:
    import importlib.util
    from pathlib import Path

    return (
        bool(model_path)
        and importlib.util.find_spec("piper") is not None
        and Path(model_path).is_file()
    )


class VoiceService:
    """Resolves the configured engines and fronts them for the API.

    ``auto``: a real engine when its library (and model) is present, else the sim
    engine in simulate mode, else unavailable. Explicit values pin one engine.

    Resolution is a cheap *plan* (importability checks); the heavy engine (an ML
    model) is constructed lazily on first use and cached — building a Core must
    never load a speech model.
    """

    def __init__(self, config: Any) -> None:
        self.config = config
        self.stt: str | None = self._plan_stt(str(getattr(config, "voice_stt", "auto")))
        self.tts: str | None = self._plan_tts(str(getattr(config, "voice_tts", "auto")))
        self._stt_engine: SttEngine | None = None
        self._tts_engine: TtsEngine | None = None
        self._sim_stt = SimStt()  # also serves the SIMVOICE bench channel

    def _plan_stt(self, mode: str) -> str | None:
        if mode == "off":
            return None
        if mode in ("whisper", "sim"):
            return mode
        # auto
        if _whisper_available():
            return "whisper"
        return "sim" if getattr(self.config, "simulate", False) else None

    def _plan_tts(self, mode: str) -> str | None:
        model_path = str(getattr(self.config, "voice_piper_model", "") or "")
        if mode == "off":
            return None
        if mode in ("piper", "sim"):
            return mode
        # auto — piper needs a configured voice model to be usable at all.
        if _piper_available(model_path):
            return "piper"
        return "sim" if getattr(self.config, "simulate", False) else None

    def _get_stt(self) -> SttEngine:
        if self._stt_engine is None:
            try:
                if self.stt == "whisper":
                    self._stt_engine = WhisperStt(str(getattr(self.config, "voice_whisper_model", "base")))
                else:
                    self._stt_engine = self._sim_stt
            except Exception as exc:
                raise VoiceError(f"speech-to-text engine failed to load: {exc}") from exc
        return self._stt_engine

    def _get_tts(self) -> TtsEngine:
        if self._tts_engine is None:
            try:
                if self.tts == "piper":
                    self._tts_engine = PiperTts(str(getattr(self.config, "voice_piper_model", "")))
                else:
                    self._tts_engine = SimTts()
            except Exception as exc:
                raise VoiceError(f"text-to-speech engine failed to load: {exc}") from exc
        return self._tts_engine

    def capabilities(self) -> dict[str, Any]:
        return {
            "stt": {"available": self.stt is not None, "engine": self.stt},
            "tts": {"available": self.tts is not None, "engine": self.tts},
        }

    async def transcribe(self, audio: bytes, content_type: str = "") -> str:
        if self.stt is None:
            raise VoiceError("no speech-to-text engine available")
        # The bench/test channel: in simulate mode a SIMVOICE canned utterance is
        # always decoded directly, whatever real engine is active — so the bench
        # keeps working when whisper is installed (mirrors sim signal injection).
        if audio.startswith(SIM_PREFIX) and getattr(self.config, "simulate", False):
            return await self._sim_stt.transcribe(audio, content_type)
        # Let the engine auto-detect the spoken language: forcing the assistant's
        # *reply* language (config.language) makes whisper translate rather than
        # transcribe when the speaker uses another language.
        return await self._get_stt().transcribe(audio, content_type, None)

    async def speak(self, text: str, voice: str | None = None) -> tuple[bytes, str]:
        if self.tts is None:
            raise VoiceError("no text-to-speech engine available")
        if not text.strip():
            raise VoiceError("nothing to say")
        return await self._get_tts().synthesize(text.strip(), voice)
