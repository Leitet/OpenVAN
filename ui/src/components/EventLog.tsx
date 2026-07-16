import type { LogEntry } from "@shared/types";
import { useT } from "../i18n";

export function EventLog({ log }: { log: LogEntry[] }) {
  const t = useT();
  return (
    <div className="log">
      <h3>{t("log.title")}</h3>
      {log.length === 0 && <p className="log-empty">{t("log.empty")}</p>}
      <ul>
        {log.map((entry) => (
          <li
            key={entry.id}
            className={
              entry.kind === "intent"
                ? entry.allowed
                  ? "log-allowed"
                  : "log-blocked"
                : "log-info"
            }
          >
            <span className="log-badge">
              {entry.kind === "intent" ? (entry.allowed ? "✓" : "⛔") : "•"}
            </span>
            {entry.text}
          </li>
        ))}
      </ul>
    </div>
  );
}
