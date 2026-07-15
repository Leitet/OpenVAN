import { useEffect, useState } from "react";
import { getSeries } from "@shared/api";
import type { TelemetryPoint } from "@shared/types";
import { Sparkline } from "./Sparkline";

interface Metric {
  key: string;
  label: string;
  unit?: string;
  min?: number;
  max?: number;
}

const METRICS: Metric[] = [
  { key: "house_battery.soc", label: "Battery", unit: "%", min: 0, max: 100 },
  { key: "solar.power", label: "Solar", unit: "W" },
  { key: "fresh_water.level_pct", label: "Fresh water", unit: "%", min: 0, max: 100 },
  { key: "grey_water.level_pct", label: "Grey water", unit: "%", min: 0, max: 100 },
  { key: "cabin.temperature", label: "Cabin", unit: "°C" },
  { key: "outside.temperature", label: "Outside", unit: "°C" },
];

const RANGES: { label: string; minutes: number; bucket?: number }[] = [
  { label: "1h", minutes: 60, bucket: 15 },
  { label: "24h", minutes: 1440 },
  { label: "7d", minutes: 10080 },
  { label: "30d", minutes: 43200 },
];

export function Trends() {
  const [data, setData] = useState<Record<string, TelemetryPoint[]>>({});
  const [rangeIdx, setRangeIdx] = useState(0);
  const range = RANGES[rangeIdx];

  useEffect(() => {
    let active = true;
    const load = async () => {
      const results = await Promise.all(
        METRICS.map((m) => getSeries(m.key, range.minutes, range.bucket)),
      );
      if (!active) return;
      const map: Record<string, TelemetryPoint[]> = {};
      METRICS.forEach((m, i) => (map[m.key] = results[i]));
      setData(map);
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [range.minutes, range.bucket]);

  return (
    <section className="panel span2">
      <div className="companion-head">
        <h2>Trends</h2>
        <div className="setting-control">
          <div className="tabs">
            {RANGES.map((r, i) => (
              <button
                key={r.label}
                className={i === rangeIdx ? "tab active" : "tab"}
                onClick={() => setRangeIdx(i)}
              >
                {r.label}
              </button>
            ))}
          </div>
          <a className="mini" href="/api/telemetry/export?minutes=1440" download>
            Export CSV
          </a>
        </div>
      </div>
      <div className="spark-grid">
        {METRICS.map((m) => (
          <Sparkline
            key={m.key}
            label={m.label}
            unit={m.unit}
            min={m.min}
            max={m.max}
            points={data[m.key] ?? []}
          />
        ))}
      </div>
    </section>
  );
}
