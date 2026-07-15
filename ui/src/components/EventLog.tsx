import type { LogEntry } from "@shared/types";

export function EventLog({ log }: { log: LogEntry[] }) {
  return (
    <div className="log">
      <h3>Activity &amp; safety</h3>
      {log.length === 0 && <p className="log-empty">No commands yet.</p>}
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
