import { Check, Ban, Dot } from "lucide-react";
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
              {entry.kind === "intent" ? (
                entry.allowed ? (
                  <Check className="log-ico" />
                ) : (
                  <Ban className="log-ico" />
                )
              ) : (
                <Dot className="log-ico" />
              )}
            </span>
            {entry.text}
          </li>
        ))}
      </ul>
    </div>
  );
}
