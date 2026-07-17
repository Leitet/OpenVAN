import { useVan, num } from "../state";
import { useT } from "../i18n";
import { Gauge } from "../components/Gauge";
import { Trends } from "../components/Trends";
import { Predictions } from "../components/Predictions";
import { Maintenance } from "../components/Maintenance";

export function PowerTab() {
  const { twin } = useVan();
  const t = useT();
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

      <Predictions />
      <Trends />
      <Maintenance />
    </div>
  );
}
