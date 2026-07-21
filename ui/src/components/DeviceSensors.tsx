import { Thermometer, Droplet, Zap, Gauge as GaugeIcon, Radio, Power } from "lucide-react";
import { sendIntent } from "@shared/api";
import { useVan } from "../state";
import { useT } from "../i18n";
import type { Entity } from "@shared/types";

// Readings from add-on devices (RuuviTag, ESPHome nodes, …) that the device_sensors
// plugin auto-surfaces. They appear only when such an integration is enabled, so this
// panel hides itself when there are none.
function iconFor(unit: string | null) {
  if (unit === "°C") return <Thermometer size={18} />;
  if (unit === "%") return <Droplet size={18} />;
  if (unit === "W" || unit === "A") return <Zap size={18} />;
  if (unit === "hPa" || unit === "V") return <GaugeIcon size={18} />;
  return <Radio size={18} />;
}

function fmt(state: unknown): string {
  if (typeof state === "number") return state.toFixed(1);
  if (typeof state === "boolean") return state ? "on" : "off";
  return String(state ?? "—");
}

export function DeviceSensors() {
  const { entities, stale } = useVan();
  const t = useT();
  const sensors = Object.values(entities)
    .filter((e: Entity) => e.attributes?.device_sensor)
    .sort((a, b) => a.name.localeCompare(b.name));
  // Controllable devices an integration registered (relays, switches) — their
  // commands go through the same safety-checked intent path as everything else.
  const controls = Object.values(entities)
    .filter((e: Entity) => e.attributes?.device_control)
    .sort((a, b) => a.name.localeCompare(b.name));

  if (sensors.length === 0 && controls.length === 0) return null;

  return (
    <section className="panel span2">
      <h2>{t("comfort.sensors")}</h2>
      {controls.length > 0 && (
        <div className="device-controls">
          {controls.map((e) => {
            const on = e.state === "on";
            return (
              <button
                key={e.entity_id}
                className={"quick device-control" + (on ? " on" : "")}
                onClick={() => sendIntent(e.entity_id, on ? "turn_off" : "turn_on")}
              >
                <Power size={20} />
                <span className="quick-label">{e.name}</span>
                <span className="quick-state">{on ? t("common.on") : t("common.off")}</span>
              </button>
            );
          })}
        </div>
      )}
      <div className="energy-stats">
        {sensors.map((e) => {
          // The provider of this reading dropped — show the last-known value
          // honestly greyed, never as a current measurement.
          const isStale = stale.has(String(e.attributes?.signal ?? ""));
          return (
            <div
              className={"energy-stat" + (isStale ? " stale" : "")}
              key={e.entity_id}
              title={isStale ? t("sensors.stale") : undefined}
            >
              <span className="energy-stat-icon">{iconFor(e.unit)}</span>
              <div>
                <div className="energy-stat-value">
                  {fmt(e.state)}
                  {e.unit && typeof e.state === "number" ? ` ${e.unit}` : ""}
                </div>
                <div className="energy-stat-label">
                  {e.name}
                  {isStale && <em className="stale-tag">{t("sensors.staleTag")}</em>}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
