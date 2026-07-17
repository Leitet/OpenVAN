import { sendIntent } from "@shared/api";
import { useVan, num } from "../state";
import { useT } from "../i18n";
import { Gauge } from "../components/Gauge";
import { HeaterControl } from "../components/HeaterControl";
import { QuickToggle } from "../components/QuickToggle";
import { AirSafety } from "../components/AirSafety";

export function ComfortTab() {
  const { entities, twin } = useVan();
  const t = useT();
  const heater = entities["climate.diesel_heater"];
  const pump = entities["switch.water_pump"];
  const pumpOn = pump?.state === "on";

  return (
    <div className="tab-grid comfort">
      <section className="panel">
        <h2>{t("comfort.climate")}</h2>
        <div className="gauge-grid">
          <Gauge label={t("label.cabin")} value={num(twin["cabin.temperature"])} unit="°C" min={-5} max={35} />
          <Gauge label={t("label.outside")} value={num(twin["outside.temperature"])} unit="°C" min={-20} max={40} />
          <Gauge label={t("label.propane")} value={num(twin["propane.level_pct"])} unit="%" warnBelow={20} />
        </div>
        <HeaterControl entity={heater} />
      </section>

      <section className="panel">
        <h2>{t("comfort.water")}</h2>
        <div className="gauge-grid">
          <Gauge label={t("label.freshWater")} value={num(twin["fresh_water.level_pct"])} unit="%" warnBelow={15} />
          <Gauge label={t("label.greyWater")} value={num(twin["grey_water.level_pct"])} unit="%" />
        </div>
        <QuickToggle
          icon="drop"
          label={t("device.waterPump")}
          state={pumpOn ? t("common.running") : t("common.off")}
          on={pumpOn}
          disabled={!pump}
          onClick={() => sendIntent("switch.water_pump", pumpOn ? "turn_off" : "turn_on")}
        />
      </section>

      <div className="span2">
        <AirSafety />
      </div>
    </div>
  );
}
