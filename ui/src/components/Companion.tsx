import { useState } from "react";
import { AlarmClock, Check } from "lucide-react";
import { ackNotice, getBriefing, snoozeNotice } from "@shared/api";
import type { Notice } from "@shared/types";
import { useT } from "../i18n";

export function Companion({ notices }: { notices: Notice[] }) {
  const t = useT();
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
        <h2>{t("companion.title")}</h2>
        <button className="briefing-btn" onClick={ask} disabled={loading}>
          {loading ? t("companion.thinking") : t("companion.briefing")}
        </button>
      </div>

      {briefing && <p className="briefing">{briefing}</p>}

      {notices.length === 0 ? (
        <p className="companion-quiet">{t("companion.allGood")}</p>
      ) : (
        <ul className="notices">
          {notices.map((n) => (
            <li key={n.key} className={"notice " + n.level}>
              <div className="notice-body">
                <div className="notice-title">{n.title}</div>
                <div className="notice-msg">{n.message}</div>
              </div>
              {/* Acknowledge: gone until it clears and fires again.
                  Snooze: gone for 4 h, whatever happens. The WS clears it. */}
              <span className="notice-actions">
                <button className="mini" title={t("notice.ack")} onClick={() => ackNotice(n.key)}>
                  <Check size={13} />
                </button>
                <button
                  className="mini"
                  title={t("notice.snooze")}
                  onClick={() => snoozeNotice(n.key)}
                >
                  <AlarmClock size={13} />
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
