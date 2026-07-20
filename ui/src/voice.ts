// Voice-chat plumbing: Core-first, browser fallback — feature-detected.
//
// Voice is an *enhancement*, never required — dictation just fills the same text
// box, so every command still goes through the safety-checked text-intent path,
// and typing works with no mic at all (Rule 2 + Rule 3).
//
// When Core exposes a REAL local engine (whisper/piper via the `voice` extra —
// GET /api/voice), we prefer it: audio stays on the van, quality is consistent,
// and it works with no internet. The browser Web Speech API remains the fallback
// (it can round-trip audio through a cloud service). Core's *sim* engines are the
// bench/test stand-ins, not speech — they're deliberately not used here.

/* eslint-disable @typescript-eslint/no-explicit-any */

import { getVoice, speakText, transcribeAudio } from "@shared/api";
import type { VoiceCaps } from "@shared/types";

// Capabilities are fetched once, in the background; until resolved (or on any
// failure) we behave exactly as before — pure browser voice.
let caps: VoiceCaps | null = null;
getVoice().then((c) => (caps = c)).catch(() => {});

const coreStt = () => caps?.stt.available && caps.stt.engine !== "sim";
const coreTts = () => caps?.tts.available && caps.tts.engine !== "sim";

export function sttSupported(): boolean {
  return (
    coreStt() === true ||
    (typeof window !== "undefined" &&
      !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition))
  );
}

export function ttsSupported(): boolean {
  return coreTts() === true || (typeof window !== "undefined" && "speechSynthesis" in window);
}

let playing: HTMLAudioElement | null = null;

/** Speak a line aloud — Core TTS when a real engine is available, else the
 * browser. No-op if neither is supported. */
export function speak(text: string): void {
  if (!text) return;
  if (coreTts()) {
    stopSpeaking();
    speakText(text)
      .then((blob) => {
        playing = new Audio(URL.createObjectURL(blob));
        playing.play().catch(() => {});
      })
      .catch(() => speakBrowser(text)); // engine hiccup → browser fallback
    return;
  }
  speakBrowser(text);
}

function speakBrowser(text: string): void {
  if (!("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = navigator.language || "en-US";
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
}

export function stopSpeaking(): void {
  if (playing) {
    playing.pause();
    playing = null;
  }
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
}

export interface Dictation {
  start(): void;
  stop(): void;
}

/** A one-shot dictation session. Returns null if no STT path is available. */
export function createDictation(opts: {
  onInterim?: (text: string) => void;
  onFinal: (text: string) => void;
  onEnd?: () => void;
  onError?: (reason: string) => void;
}): Dictation | null {
  // Core path: record the mic locally, transcribe on the van.
  if (coreStt() && typeof navigator !== "undefined" && !!navigator.mediaDevices) {
    return createCoreDictation(opts);
  }
  return createBrowserDictation(opts);
}

function createCoreDictation(opts: {
  onInterim?: (text: string) => void;
  onFinal: (text: string) => void;
  onEnd?: () => void;
  onError?: (reason: string) => void;
}): Dictation {
  let recorder: MediaRecorder | null = null;
  let stream: MediaStream | null = null;
  const chunks: Blob[] = [];

  const cleanup = () => {
    stream?.getTracks().forEach((t) => t.stop());
    recorder = null;
    stream = null;
    opts.onEnd?.();
  };

  return {
    start() {
      navigator.mediaDevices
        .getUserMedia({ audio: true })
        .then((s) => {
          stream = s;
          recorder = new MediaRecorder(s);
          recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
          recorder.onstop = async () => {
            try {
              const text = await transcribeAudio(new Blob(chunks, { type: recorder?.mimeType }));
              if (text.trim()) opts.onFinal(text.trim());
            } catch (e: any) {
              opts.onError?.(String(e?.message ?? e));
            } finally {
              cleanup();
            }
          };
          recorder.start();
        })
        .catch((e) => {
          opts.onError?.(String(e?.message ?? "microphone unavailable"));
          cleanup();
        });
    },
    stop() {
      recorder?.stop();
    },
  };
}

function createBrowserDictation(opts: {
  onInterim?: (text: string) => void;
  onFinal: (text: string) => void;
  onEnd?: () => void;
  onError?: (reason: string) => void;
}): Dictation | null {
  const Ctor: any =
    (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
  if (!Ctor) return null;

  const rec: any = new Ctor();
  rec.lang = navigator.language || "en-US";
  rec.interimResults = true;
  rec.continuous = false;
  rec.maxAlternatives = 1;

  rec.onresult = (ev: any) => {
    let interim = "";
    let final = "";
    for (let i = ev.resultIndex; i < ev.results.length; i++) {
      const chunk = ev.results[i][0].transcript;
      if (ev.results[i].isFinal) final += chunk;
      else interim += chunk;
    }
    if (interim && opts.onInterim) opts.onInterim(interim);
    if (final.trim()) opts.onFinal(final.trim());
  };
  rec.onerror = (ev: any) => opts.onError?.(ev?.error ?? "error");
  rec.onend = () => opts.onEnd?.();

  return {
    start: () => rec.start(),
    stop: () => rec.stop(),
  };
}
