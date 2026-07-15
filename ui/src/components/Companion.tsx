import { useState } from "react";
import { getBriefing } from "@shared/api";
import type { Notice } from "@shared/types";

export function Companion({ notices }: { notices: Notice[] }) {
  const [briefing, setBriefing] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const ask = async () => {
    setLoading(true);
    try {
      setBriefing(await getBriefing());
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="companion">
      <div className="companion-head">
        <h2>Companion</h2>
        <button className="briefing-btn" onClick={ask} disabled={loading}>
          {loading ? "Thinking…" : "Ask for a briefing"}
        </button>
      </div>

      {briefing && <p className="briefing">{briefing}</p>}

      {notices.length === 0 ? (
        <p className="companion-quiet">All good — nothing needs your attention.</p>
      ) : (
        <ul className="notices">
          {notices.map((n) => (
            <li key={n.key} className={"notice " + n.level}>
              <div className="notice-title">{n.title}</div>
              <div className="notice-msg">{n.message}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
