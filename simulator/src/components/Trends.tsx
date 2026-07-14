import { useEffect, useState } from "react";
import { getSeries } from "../api";
import type { TelemetryPoint } from "../types";
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

export function Trends() {
  const [data, setData] = useState<Record<string, TelemetryPoint[]>>({});

  useEffect(() => {
    let active = true;
    const load = async () => {
      const results = await Promise.all(
        METRICS.map((m) => getSeries(m.key, 60, 15)),
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
  }, []);

  return (
    <section className="panel span2">
      <div className="companion-head">
        <h2>Trends · last hour</h2>
        <a className="mini" href="/api/telemetry/export?minutes=1440" download>
          Export CSV (24h)
        </a>
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
