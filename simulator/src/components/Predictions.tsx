import { useEffect, useState } from "react";
import { getPredictions } from "../api";

function fmtHours(h: number): string {
  if (h < 1) return `${Math.round(h * 60)} min`;
  if (h < 48) return `${h.toFixed(1)} h`;
  return `${(h / 24).toFixed(1)} days`;
}

export function Predictions() {
  const [p, setP] = useState<Record<string, number>>({});

  useEffect(() => {
    let active = true;
    const load = async () => {
      const data = await getPredictions();
      if (active) setP(data);
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  const rows: { label: string; value: string }[] = [];
  if (p.battery_empty_hours !== undefined)
    rows.push({ label: "Battery empty in", value: fmtHours(p.battery_empty_hours) });
  if (p.fresh_water_empty_hours !== undefined)
    rows.push({ label: "Fresh water empty in", value: fmtHours(p.fresh_water_empty_hours) });
  if (p.grey_water_full_hours !== undefined)
    rows.push({ label: "Grey tank full in", value: fmtHours(p.grey_water_full_hours) });
  if (p.diesel_empty_hours !== undefined)
    rows.push({ label: "Diesel empty in", value: fmtHours(p.diesel_empty_hours) });
  if (p.solar_wh_24h !== undefined)
    rows.push({ label: "Solar (last 24h)", value: `${p.solar_wh_24h.toFixed(0)} Wh` });

  return (
    <section className="panel">
      <h2>Predictions</h2>
      {rows.length === 0 ? (
        <p className="companion-quiet">
          Not enough history yet — trends appear as signals change.
        </p>
      ) : (
        <ul className="pred-list">
          {rows.map((r) => (
            <li key={r.label}>
              <span className="pred-label">{r.label}</span>
              <span className="pred-value">{r.value}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
