import { Zap, Fuel, PlugZap, Power } from "lucide-react";
import { useVan, num } from "../state";
import { useT } from "../i18n";
import { Gauge } from "../components/Gauge";
import { Trends } from "../components/Trends";
import { Predictions } from "../components/Predictions";
import { Maintenance } from "../components/Maintenance";

function EnergyStat({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone?: "good" | "muted";
}) {
  return (
    <div className={"energy-stat" + (tone ? ` ${tone}` : "")}>
      <span className="energy-stat-icon">{icon}</span>
      <div>
        <div className="energy-stat-value">{value}</div>
        <div className="energy-stat-label">{label}</div>
      </div>
    </div>
  );
}

export function PowerTab() {
  const { twin } = useVan();
  const t = useT();
  const yieldWh = num(twin["solar.yield_today_wh"]);
  const alt = num(twin["alternator.power"]);
  const shore = Boolean(twin["shore.connected"]);
  const inverterOn = Boolean(twin["inverter.on"]);
  const invTemp = num(twin["inverter.temperature"]);
  return (
    <div className="tab-grid power">
      <section className="panel">
        <h2>{t("power.energy")}</h2>
        <div className="gauge-grid">
          <Gauge label={t("label.battery")} value={num(twin["house_battery.soc"])} unit="%" warnBelow={20} />
          <Gauge label={t("label.voltage")} value={num(twin["house_battery.voltage"])} unit="V" min={10} max={15} />
          <Gauge label={t("label.solar")} value={num(twin["solar.power"])} unit="W" min={0} max={600} />
          <Gauge label={t("label.heaterDraw")} value={num(twin["diesel_heater.power"])} unit="W" min={0} max={120} />
          <Gauge label={t("label.fridge")} value={num(twin["fridge.temp_c"])} unit="°C" min={-5} max={20} />
          <Gauge label={t("label.fridgeDraw")} value={num(twin["fridge.power"])} unit="W" min={0} max={120} />
        </div>
      </section>

      <section className="panel">
        <h2>{t("power.system")}</h2>
        <div className="energy-stats">
          <EnergyStat
            icon={<Zap size={18} />}
            label={t("label.solarYield")}
            value={yieldWh !== undefined ? `${(yieldWh / 1000).toFixed(2)} kWh` : "—"}
          />
          <EnergyStat
            icon={<Fuel size={18} />}
            label={t("label.alternator")}
            value={alt !== undefined ? `${alt.toFixed(0)} W` : "—"}
            tone={alt && alt > 0 ? "good" : "muted"}
          />
          <EnergyStat
            icon={<PlugZap size={18} />}
            label={t("label.shore")}
            value={shore ? t("state.connected") : t("state.disconnected")}
            tone={shore ? "good" : "muted"}
          />
          <EnergyStat
            icon={<Power size={18} />}
            label={t("label.inverter")}
            value={inverterOn ? t("state.on") : t("state.off")}
            tone={inverterOn ? "good" : "muted"}
          />
          <EnergyStat
            icon={<Power size={18} />}
            label={t("label.inverterTemp")}
            value={invTemp !== undefined ? `${invTemp.toFixed(1)} °C` : "—"}
          />
        </div>
      </section>

      {/* Predictions + Maintenance share a row (no ragged hole); Trends spans last. */}
      <Predictions />
      <Maintenance />
      <Trends />
    </div>
  );
}
