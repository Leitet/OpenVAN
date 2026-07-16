// Voice-chat plumbing over the browser Web Speech API, feature-detected.
//
// Voice is an *enhancement*, never required — dictation just fills the same text
// box, so every command still goes through the safety-checked text-intent path,
// and typing works with no mic at all (Rule 2 + Rule 3). Browser STT quality
// varies and can use a cloud service; a fully offline path (whisper.cpp / vosk
// for STT, piper for TTS, or a cloud realtime model) is a Core-side follow-up —
// see backlog.md. This module is the front-end seam that work will plug into.

/* eslint-disable @typescript-eslint/no-explicit-any */

export function sttSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)
  );
}

export function ttsSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

/** Speak a line aloud (on-device TTS). No-op if unsupported. */
export function speak(text: string): void {
  if (!ttsSupported() || !text) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = navigator.language || "en-US";
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
}

export function stopSpeaking(): void {
  if (ttsSupported()) window.speechSynthesis.cancel();
}

export interface Dictation {
  start(): void;
  stop(): void;
}

/** A one-shot dictation session. Returns null if STT isn't available. */
export function createDictation(opts: {
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
