"""Voice pipeline: sim engines (the Rule-1 stand-in), engine resolution, and the
HTTP surface. Real whisper/piper are optional extras validated on real hardware."""

from __future__ import annotations

import io
import wave

import pytest
from fastapi.testclient import TestClient

from openvan_core.api import build_app
from openvan_core.config import Config
from openvan_core.voice import SIM_PREFIX, SimStt, SimTts, VoiceError, VoiceService


# --- sim engines -------------------------------------------------------------

async def test_sim_stt_decodes_canned_utterance():
    stt = SimStt()
    text = await stt.transcribe(SIM_PREFIX + "turn on the cabin light".encode())
    assert text == "turn on the cabin light"


async def test_sim_stt_rejects_real_audio():
    with pytest.raises(VoiceError):
        await SimStt().transcribe(b"\x00\x01\x02 not sim audio")


async def test_sim_tts_renders_playable_wav():
    audio, mime = await SimTts().synthesize("hello there travelling friend")
    assert mime == "audio/wav"
    with wave.open(io.BytesIO(audio), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == SimTts.RATE
        assert w.getnframes() > 0
    # Deterministic (no wall-clock/RNG) and longer text → longer audio.
    again, _ = await SimTts().synthesize("hello there travelling friend")
    assert again == audio
    short, _ = await SimTts().synthesize("hi")
    assert len(short) < len(audio)


# --- engine resolution -------------------------------------------------------
# Availability is monkeypatched so these hold whether or not the optional
# whisper/piper extras happen to be installed in the dev env.

def _no_engines(monkeypatch):
    import openvan_core.voice as v

    monkeypatch.setattr(v, "_whisper_available", lambda: False)
    monkeypatch.setattr(v, "_piper_available", lambda _p: False)


def test_auto_resolves_to_sim_in_simulate_mode(monkeypatch):
    _no_engines(monkeypatch)
    caps = VoiceService(Config(simulate=True)).capabilities()
    assert caps["stt"] == {"available": True, "engine": "sim"}
    assert caps["tts"] == {"available": True, "engine": "sim"}


def test_auto_prefers_real_engines_when_installed(monkeypatch):
    import openvan_core.voice as v

    monkeypatch.setattr(v, "_whisper_available", lambda: True)
    monkeypatch.setattr(v, "_piper_available", lambda _p: True)
    svc = VoiceService(Config(simulate=True, voice_piper_model="/tmp/voice.onnx"))
    caps = svc.capabilities()
    assert caps["stt"]["engine"] == "whisper"
    assert caps["tts"]["engine"] == "piper"


def test_auto_unavailable_on_a_real_van_without_engines(monkeypatch):
    _no_engines(monkeypatch)
    # simulate=False and no optional libs → voice reports unavailable (the
    # front-end then keeps the browser speech APIs; text always works).
    caps = VoiceService(Config(simulate=False)).capabilities()
    assert caps["stt"]["available"] is False
    assert caps["tts"]["available"] is False


async def test_simvoice_bypass_reaches_sim_even_with_a_real_engine(monkeypatch):
    # The bench's canned-utterance channel must keep working when whisper is the
    # active engine (in simulate mode) — it bypasses straight to the sim decoder,
    # never loading the model.
    import openvan_core.voice as v

    monkeypatch.setattr(v, "_whisper_available", lambda: True)
    svc = VoiceService(Config(simulate=True))
    assert svc.stt == "whisper"
    text = await svc.transcribe(SIM_PREFIX + b"dim the lights")
    assert text == "dim the lights"
    assert svc._stt_engine is None  # the heavy engine was never constructed


def test_off_pins_engines_off():
    svc = VoiceService(Config(simulate=True, voice_stt="off", voice_tts="off"))
    assert svc.stt is None and svc.tts is None


def test_building_a_service_never_loads_an_engine(monkeypatch):
    # Lazy by design: resolution is a cheap plan; the ML model loads on first use.
    import openvan_core.voice as v

    def boom(*a, **k):
        raise AssertionError("engine constructed eagerly")

    monkeypatch.setattr(v, "WhisperStt", boom)
    monkeypatch.setattr(v, "PiperTts", boom)
    monkeypatch.setattr(v, "_whisper_available", lambda: True)
    monkeypatch.setattr(v, "_piper_available", lambda _p: True)
    svc = VoiceService(Config(simulate=True, voice_piper_model="/tmp/x.onnx"))
    assert svc.capabilities()["stt"]["engine"] == "whisper"  # plan only, no load


async def test_service_raises_cleanly_when_off():
    svc = VoiceService(Config(simulate=True, voice_stt="off", voice_tts="off"))
    with pytest.raises(VoiceError):
        await svc.transcribe(b"SIMVOICE:hi")
    with pytest.raises(VoiceError):
        await svc.speak("hi")


# --- HTTP surface ------------------------------------------------------------

def _cfg(tmp_path, **kw):
    # Engines pinned to sim so the HTTP tests are deterministic regardless of
    # which optional extras are installed.
    kw.setdefault("voice_stt", "sim")
    kw.setdefault("voice_tts", "sim")
    return Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
                  telemetry_enabled=False, simulate=True, data_dir=tmp_path, **kw)


def test_voice_http_roundtrip(tmp_path):
    with TestClient(build_app(_cfg(tmp_path))) as client:
        caps = client.get("/api/voice").json()
        assert caps["stt"]["engine"] == "sim" and caps["tts"]["engine"] == "sim"

        out = client.post(
            "/api/voice/transcribe",
            content=b"SIMVOICE:good morning van",
            headers={"Content-Type": "application/octet-stream"},
        )
        assert out.status_code == 200 and out.json()["text"] == "good morning van"

        # Garbage audio → a clean 400, not a 500.
        bad = client.post("/api/voice/transcribe", content=b"\x00\x01")
        assert bad.status_code == 400

        spoken = client.post("/api/voice/speak", json={"text": "hello"})
        assert spoken.status_code == 200
        assert spoken.headers["content-type"].startswith("audio/wav")
        with wave.open(io.BytesIO(spoken.content), "rb") as w:
            assert w.getnframes() > 0


def test_voice_http_unavailable(tmp_path):
    cfg = _cfg(tmp_path, voice_stt="off", voice_tts="off")
    with TestClient(build_app(cfg)) as client:
        assert client.get("/api/voice").json()["stt"]["available"] is False
        assert client.post("/api/voice/transcribe", content=b"SIMVOICE:x").status_code == 503
        assert client.post("/api/voice/speak", json={"text": "x"}).status_code == 503
