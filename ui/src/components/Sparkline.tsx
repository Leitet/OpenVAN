import type { TelemetryPoint } from "@shared/types";

interface SparklineProps {
  label: string;
  unit?: string;
  points: TelemetryPoint[];
  min?: number;
  max?: number;
}

const W = 160;
const H = 40;

/** Minimal hand-drawn SVG line chart — matches the gauges/van-view style. */
export function Sparkline({ label, unit, points, min, max }: SparklineProps) {
  const values = points.map((p) => p.v);
  const current = values.length ? values[values.length - 1] : undefined;

  let path = "";
  if (points.length >= 2) {
    const lo = min ?? Math.min(...values);
    const hi = max ?? Math.max(...values);
    const span = hi - lo || 1;
    const t0 = points[0].t;
    const t1 = points[points.length - 1].t;
    const tspan = t1 - t0 || 1;
    path = points
      .map((p) => {
        const x = ((p.t - t0) / tspan) * W;
        const y = H - ((p.v - lo) / span) * H;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }

  return (
    <div className="spark">
      <div className="spark-head">
        <span className="spark-label">{label}</span>
        <span className="spark-value">
          {current === undefined ? "—" : current.toFixed(1)}
          {unit ?? ""}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="spark-svg">
        {path ? (
          <polyline points={path} className="spark-line" />
        ) : (
          <text x={W / 2} y={H / 2} className="spark-empty">
            collecting…
          </text>
        )}
      </svg>
    </div>
  );
}
