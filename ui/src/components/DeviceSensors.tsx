import { Thermometer, Droplet, Zap, Gauge as GaugeIcon, Radio } from "lucide-react";
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
  const { entities } = useVan();
  const t = useT();
  const sensors = Object.values(entities)
    .filter((e: Entity) => e.attributes?.device_sensor)
    .sort((a, b) => a.name.localeCompare(b.name));

  if (sensors.length === 0) return null;

  return (
    <section className="panel span2">
      <h2>{t("comfort.sensors")}</h2>
      <div className="energy-stats">
        {sensors.map((e) => (
          <div className="energy-stat" key={e.entity_id}>
            <span className="energy-stat-icon">{iconFor(e.unit)}</span>
            <div>
              <div className="energy-stat-value">
                {fmt(e.state)}
                {e.unit && typeof e.state === "number" ? ` ${e.unit}` : ""}
              </div>
              <div className="energy-stat-label">{e.name}</div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
