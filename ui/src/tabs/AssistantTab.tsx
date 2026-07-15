import { useState } from "react";
import { sendText } from "@shared/api";
import { useVan } from "../state";
import { Companion } from "../components/Companion";

export function AssistantTab() {
  const { notices, assistant } = useVan();
  const [text, setText] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (text.trim()) sendText(text.trim());
    setText("");
  };

  return (
    <div className="tab-grid stack">
      <section className="panel">
        <Companion notices={notices} />
        <form className="text-cmd" onSubmit={submit}>
          <input
            placeholder={
              assistant.llm
                ? 'Ask anything, e.g. "it\'s freezing, warm it up"'
                : 'Try "turn on the cabin light"'
            }
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <button type="submit">Send</button>
        </form>
      </section>
    </div>
  );
}
