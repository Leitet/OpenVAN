import { useEffect, useState } from "react";
import { getPredictions } from "@shared/api";
import { useT, type TFn } from "../i18n";

function fmtHours(h: number, t: TFn): string {
  if (h < 1) return `${Math.round(h * 60)} ${t("units.min")}`;
  if (h < 48) return `${h.toFixed(1)} ${t("units.h")}`;
  return `${(h / 24).toFixed(1)} ${t("units.days")}`;
}

export function Predictions() {
  const t = useT();
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
    rows.push({ label: t("predictions.batteryEmpty"), value: fmtHours(p.battery_empty_hours, t) });
  if (p.fresh_water_empty_hours !== undefined)
    rows.push({ label: t("predictions.freshWaterEmpty"), value: fmtHours(p.fresh_water_empty_hours, t) });
  if (p.grey_water_full_hours !== undefined)
    rows.push({ label: t("predictions.greyFull"), value: fmtHours(p.grey_water_full_hours, t) });
  if (p.diesel_empty_hours !== undefined)
    rows.push({ label: t("predictions.dieselEmpty"), value: fmtHours(p.diesel_empty_hours, t) });
  if (p.solar_wh_24h !== undefined)
    rows.push({ label: t("predictions.solar24h"), value: `${p.solar_wh_24h.toFixed(0)} Wh` });

  return (
    <section className="panel">
      <h2>{t("predictions.title")}</h2>
      {rows.length === 0 ? (
        <p className="companion-quiet">{t("predictions.notEnough")}</p>
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
