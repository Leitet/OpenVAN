import { useMemo, useState } from "react";
import { injectSignal } from "@shared/api";
import type { Twin } from "@shared/types";

// The plug-and-play injector: every twin signal — whoever provides it — gets an
// auto-generated control, grouped by its data source (integration id, plugin,
// seed). A brand-new integration's signals appear here the moment it emits
// them, with zero bench code. The hand-crafted sliders above stay for the
// curated scenarios; this browser guarantees full coverage.

function NumberControl({ signalKey, value }: { signalKey: string; value: number }) {
  const [draft, setDraft] = useState<string | null>(null);
  const commit = () => {
    if (draft !== null && draft !== "" && Number.isFinite(Number(draft))) {
      injectSignal(signalKey, Number(draft));
    }
    setDraft(null);
  };
  return (
    <input
      className="sig-input"
      type="number"
      value={draft ?? String(value)}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
    />
  );
}

function TextControl({ signalKey, value }: { signalKey: string; value: string }) {
  const [draft, setDraft] = useState<string | null>(null);
  const commit = () => {
    if (draft !== null) injectSignal(signalKey, draft);
    setDraft(null);
  };
  return (
    <input
      className="sig-input sig-text"
      type="text"
      value={draft ?? value}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
    />
  );
}

function SignalRow({ signalKey, value }: { signalKey: string; value: unknown }) {
  let control: React.ReactNode;
  if (typeof value === "boolean") {
    control = (
      <button
        className={"sig-toggle" + (value ? " on" : "")}
        onClick={() => injectSignal(signalKey, !value)}
      >
        {value ? "true" : "false"}
      </button>
    );
  } else if (typeof value === "number") {
    control = <NumberControl signalKey={signalKey} value={value} />;
  } else if (typeof value === "string") {
    control = <TextControl signalKey={signalKey} value={value} />;
  } else {
    control = <span className="sig-unknown">unknown</span>;
  }
  return (
    <div className="sig-row">
      <code className="sig-key">{signalKey}</code>
      {control}
    </div>
  );
}

export function SignalBrowser({
  twin,
  sources,
}: {
  twin: Twin;
  sources: Record<string, string>;
}) {
  const [filter, setFilter] = useState("");

  const groups = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    const bySource = new Map<string, [string, unknown][]>();
    for (const key of Object.keys(twin).sort()) {
      if (needle && !key.toLowerCase().includes(needle)) continue;
      const source = sources[key] ?? "unknown";
      if (!bySource.has(source)) bySource.set(source, []);
      bySource.get(source)!.push([key, twin[key]]);
    }
    return [...bySource.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [twin, sources, filter]);

  return (
    <div className="signal-browser">
      <input
        className="sig-filter"
        type="search"
        placeholder="Filter signals…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />
      {groups.map(([source, entries]) => (
        <details key={source} open={Boolean(filter)}>
          <summary>
            {source} <em>({entries.length})</em>
          </summary>
          {entries.map(([key, value]) => (
            <SignalRow key={key} signalKey={key} value={value} />
          ))}
        </details>
      ))}
      {groups.length === 0 && <p className="sig-empty">No matching signals.</p>}
    </div>
  );
}
