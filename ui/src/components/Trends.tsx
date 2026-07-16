import { useEffect, useState } from "react";
import { getSeries } from "@shared/api";
import type { TelemetryPoint } from "@shared/types";
import { useT } from "../i18n";
import { Sparkline } from "./Sparkline";

interface Metric {
  key: string;
  labelKey: string;
  unit?: string;
  min?: number;
  max?: number;
}

const METRICS: Metric[] = [
  { key: "house_battery.soc", labelKey: "label.battery", unit: "%", min: 0, max: 100 },
  { key: "solar.power", labelKey: "label.solar", unit: "W" },
  { key: "fresh_water.level_pct", labelKey: "label.freshWater", unit: "%", min: 0, max: 100 },
  { key: "grey_water.level_pct", labelKey: "label.greyWater", unit: "%", min: 0, max: 100 },
  { key: "cabin.temperature", labelKey: "label.cabin", unit: "°C" },
  { key: "outside.temperature", labelKey: "label.outside", unit: "°C" },
];

const RANGES: { label: string; minutes: number; bucket?: number }[] = [
  { label: "1h", minutes: 60, bucket: 15 },
  { label: "24h", minutes: 1440 },
  { label: "7d", minutes: 10080 },
  { label: "30d", minutes: 43200 },
];

export function Trends() {
  const t = useT();
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
        <h2>{t("trends.title")}</h2>
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
            {t("trends.exportCsv")}
          </a>
        </div>
      </div>
      <div className="spark-grid">
        {METRICS.map((m) => (
          <Sparkline
            key={m.key}
            label={t(m.labelKey)}
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
