interface GaugeProps {
  label: string;
  value: number | undefined;
  unit?: string | null;
  min?: number;
  max?: number;
  warnBelow?: number;
}

export function Gauge({ label, value, unit, min = 0, max = 100, warnBelow }: GaugeProps) {
  const v = typeof value === "number" ? value : NaN;
  const pct = Number.isNaN(v) ? 0 : Math.max(0, Math.min(100, ((v - min) / (max - min)) * 100));
  const warn = warnBelow !== undefined && !Number.isNaN(v) && v < warnBelow;

  return (
    <div className="gauge">
      <div className="gauge-label">{label}</div>
      <div className="gauge-value">
        {Number.isNaN(v) ? "—" : v.toFixed(1)}
        <span className="gauge-unit">{unit ?? ""}</span>
      </div>
      <div className="gauge-track">
        <div
          className={"gauge-fill" + (warn ? " warn" : "")}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
