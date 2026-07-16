import { useEffect, useRef, useState } from "react";
import { sendChat, getBriefing } from "@shared/api";
import type { Assistant, Notice } from "@shared/types";
import {
  createDictation,
  speak,
  sttSupported,
  ttsSupported,
  type Dictation,
} from "../voice";
import { useT } from "../i18n";

interface Msg {
  id: number;
  role: "user" | "assistant";
  text: string;
  blocked?: boolean;
}

let counter = 0;

/**
 * Conversational transcript for the Assistant tab. Each command runs through the
 * same safety-checked text-intent path — the reply is Core's own `reason` (what it
 * did, or why it refused). Voice (dictation + spoken replies) is an optional layer
 * on top of that same path; text always works with no mic (Rule 2 + Rule 3).
 */
export function Chat({ notices, assistant }: { notices: Notice[]; assistant: Assistant }) {
  const t = useT();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [speakReplies, setSpeakReplies] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const dictationRef = useRef<Dictation | null>(null);
  const speakRef = useRef(speakReplies);
  speakRef.current = speakReplies;

  const canDictate = sttSupported();
  const canSpeak = ttsSupported();

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  const push = (m: Omit<Msg, "id">) => setMsgs((prev) => [...prev, { ...m, id: counter++ }]);

  const say = (text: string) => {
    push({ role: "assistant", text });
    if (speakRef.current) speak(text);
  };

  const submit = async (raw: string) => {
    const q = raw.trim();
    if (!q || busy) return;
    setText("");
    push({ role: "user", text: q });
    setBusy(true);
    try {
      const r = await sendChat(q);
      const reply = r.reply?.trim() || "…";
      push({ role: "assistant", text: reply, blocked: r.blocked_by_safety || !r.ok });
      if (speakRef.current) speak(reply);
    } catch {
      push({ role: "assistant", text: t("chat.unreachable"), blocked: true });
    } finally {
      setBusy(false);
    }
  };

  const briefing = async () => {
    if (busy) return;
    setBusy(true);
    try {
      say(await getBriefing());
    } catch {
      push({ role: "assistant", text: t("chat.unreachable"), blocked: true });
    } finally {
      setBusy(false);
    }
  };

  const toggleMic = () => {
    if (listening) {
      dictationRef.current?.stop();
      setListening(false);
      return;
    }
    const d = createDictation({
      onInterim: (t) => setText(t),
      onFinal: (t) => {
        setListening(false);
        submit(t);
      },
      onEnd: () => setListening(false),
      onError: () => setListening(false),
    });
    if (!d) return;
    dictationRef.current = d;
    setListening(true);
    setText("");
    d.start();
  };

  return (
    <section className="panel chat">
      <div className="companion-head">
        <div className="chat-title">
          <h2>{t("assistant.title")}</h2>
          <span className={"chat-target" + (assistant.llm ? " on" : "")} title={t("chat.whichModel")}>
            {assistant.llm
              ? `${assistant.connectivity === "online" ? "☁ " + t("ai.cloud") : "⌂ " + t("ai.local")} · ${assistant.model}`
              : t("chat.rulesNoModel")}
          </span>
        </div>
        <div className="chat-actions">
          {canSpeak && (
            <button
              className={"mini" + (speakReplies ? " on" : "")}
              onClick={() => setSpeakReplies((v) => !v)}
              title={t("chat.speak")}
            >
              {speakReplies ? "🔊 " + t("chat.speaking") : "🔈 " + t("chat.speak")}
            </button>
          )}
          <button className="briefing-btn" onClick={briefing} disabled={busy}>
            {busy ? t("companion.thinking") : t("companion.briefing")}
          </button>
        </div>
      </div>

      {notices.length > 0 && (
        <ul className="notices">
          {notices.map((n) => (
            <li key={n.key} className={"notice " + n.level}>
              <div className="notice-title">{n.title}</div>
              <div className="notice-msg">{n.message}</div>
            </li>
          ))}
        </ul>
      )}

      <div className="chat-log">
        {msgs.length === 0 ? (
          <p className="chat-empty">
            {assistant.llm
              ? assistant.personality
                ? t("chat.emptyLlmPersona", { name: assistant.personality })
                : t("chat.emptyLlm")
              : t("chat.emptyRules")}
            {canDictate ? " " + t("chat.tapMic") : ""}
          </p>
        ) : (
          msgs.map((m) => (
            <div key={m.id} className={"bubble " + m.role + (m.blocked ? " blocked" : "")}>
              {m.text}
            </div>
          ))
        )}
        {busy && (
          <div className="bubble assistant thinking">
            {assistant.personality && <span className="think-who">{assistant.personality}</span>}
            <span className="think-dots" aria-label={t("companion.thinking")}>
              <i />
              <i />
              <i />
            </span>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form
        className="text-cmd"
        onSubmit={(e) => {
          e.preventDefault();
          submit(text);
        }}
      >
        {canDictate && (
          <button
            type="button"
            className={"mic" + (listening ? " on" : "")}
            onClick={toggleMic}
            title={listening ? "Stop listening" : "Speak"}
            aria-label="Voice input"
          >
            {listening ? "●" : "🎤"}
          </button>
        )}
        <input
          placeholder={
            listening
              ? t("chat.listening")
              : assistant.llm
                ? t("chat.askAnything")
                : t("chat.tryCommand")
          }
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <button type="submit" disabled={busy}>
          {t("common.send")}
        </button>
      </form>
    </section>
  );
}
