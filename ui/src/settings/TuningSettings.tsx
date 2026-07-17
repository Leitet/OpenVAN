import { useEffect, useState } from "react";
import { useSettings } from "./SettingsProvider";
import { useT } from "../i18n";

// Every advisor threshold, scene setpoint, leveling dimension and maintenance
// interval — editable, defaulted, and reset-able. Nothing is hardcoded in Core;
// these edit the same values the backend defaults from.
type Field = [key: string, label: string, unit: string];

const GROUPS: { title: string; fields: Field[] }[] = [
  {
    title: "Air & safety",
    fields: [
      ["co_warn_ppm", "CO warning", "ppm"],
      ["co_danger_ppm", "CO danger", "ppm"],
      ["gas_leak_lel", "Gas leak", "%LEL"],
      ["co2_high_ppm", "CO₂ stuffy", "ppm"],
      ["condensation_humidity_pct", "Condensation humidity", "%"],
      ["condensation_margin_c", "Condensation margin", "°C"],
      ["cabin_cold_c", "Cabin too cold", "°C"],
      ["cabin_hot_c", "Cabin too hot", "°C"],
    ],
  },
  { title: "Fridge", fields: [["fridge_warm_c", "Fridge warm", "°C"]] },
  { title: "Propane", fields: [["propane_low_pct", "Propane low", "%"]] },
  {
    title: "Leveling",
    fields: [
      ["level_threshold_deg", "Off-level threshold", "°"],
      ["level_track_m", "Track width", "m"],
      ["level_wheelbase_m", "Wheelbase", "m"],
    ],
  },
  {
    title: "Scenes",
    fields: [
      ["scene_sleep_c", "Sleep setpoint", "°C"],
      ["scene_comfort_c", "Comfort setpoint", "°C"],
    ],
  },
  {
    title: "Water · energy · journey",
    fields: [
      ["fresh_water_low_pct", "Fresh water low", "%"],
      ["grey_water_full_pct", "Grey tank full", "%"],
      ["diesel_low_pct", "Diesel low", "%"],
      ["battery_low_hours", "Battery runtime low", "h"],
      ["long_drive_hours", "Long drive", "h"],
      ["rain_soon_hours", "Rain soon", "h"],
    ],
  },
];

const MAINT: [id: string, label: string, unit: string, def: number][] = [
  ["engine_service", "Engine service", "km", 15000],
  ["tyre_rotation", "Tyre rotation", "km", 10000],
  ["brake_check", "Brake inspection", "km", 30000],
  ["gas_inspection", "Gas inspection", "days", 365],
  ["damp_check", "Damp check", "days", 365],
  ["alarm_test", "Alarm test", "days", 180],
];

export function TuningSettings() {
  const { settings, patch } = useSettings();
  const t = useT();
  const [draft, setDraft] = useState<Record<string, number>>({});
  const [maint, setMaint] = useState<Record<string, number>>({});

  useEffect(() => {
    if (!settings) return;
    setDraft({ ...settings.tuning_defaults, ...settings.tuning });
    const m: Record<string, number> = {};
    for (const [id, , , def] of MAINT) m[id] = settings.maintenance_intervals[id] ?? def;
    setMaint(m);
  }, [settings]);

  if (!settings) return null;

  const commit = (key: string, value: number) => {
    if (Number.isFinite(value)) patch({ tuning: { [key]: value } });
  };
  const commitMaint = (id: string, value: number) => {
    if (Number.isFinite(value)) patch({ maintenance_intervals: { [id]: value } });
  };
  const resetAll = () => patch({ tuning: settings.tuning_defaults });

  return (
    <div className="tuning">
      <p className="hint">{t("tuning.hint")}</p>
      {GROUPS.map((g) => (
        <section className="panel tuning-group" key={g.title}>
          <h3>{g.title}</h3>
          <div className="tuning-grid">
            {g.fields.map(([key, label, unit]) => (
              <label className="tuning-field" key={key}>
                <span>{label}</span>
                <span className="tuning-input">
                  <input
                    type="number"
                    value={draft[key] ?? ""}
                    onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.valueAsNumber }))}
                    onBlur={(e) => commit(key, e.target.valueAsNumber)}
                  />
                  <em>{unit}</em>
                </span>
              </label>
            ))}
          </div>
        </section>
      ))}

      <section className="panel tuning-group">
        <h3>{t("maint.title")}</h3>
        <div className="tuning-grid">
          {MAINT.map(([id, label, unit]) => (
            <label className="tuning-field" key={id}>
              <span>{label}</span>
              <span className="tuning-input">
                <input
                  type="number"
                  value={maint[id] ?? ""}
                  onChange={(e) => setMaint((m) => ({ ...m, [id]: e.target.valueAsNumber }))}
                  onBlur={(e) => commitMaint(id, e.target.valueAsNumber)}
                />
                <em>{unit}</em>
              </span>
            </label>
          ))}
        </div>
      </section>

      <button className="mini" onClick={resetAll}>
        {t("tuning.reset")}
      </button>
    </div>
  );
}
