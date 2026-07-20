import { sendIntent } from "@shared/api";
import { useVan, num } from "../state";
import { useT } from "../i18n";
import { Gauge } from "../components/Gauge";
import { QuickToggle } from "../components/QuickToggle";
import { Companion } from "../components/Companion";
import { Scenes } from "../components/Scenes";

export function HomeTab() {
  const { entities, twin, notices } = useVan();
  const t = useT();
  const soc = num(twin["house_battery.soc"]);
  const light = entities["light.cabin"];
  const lightOn = light?.state === "on";
  const heater = entities["climate.diesel_heater"];
  const heaterOn = heater?.state === "heating";
  const pump = entities["switch.water_pump"];
  const pumpOn = pump?.state === "on";

  return (
    <div className="tab-grid fill home">
      <section className="panel">
        <h2>{t("home.vitals")}</h2>
        <div className="gauge-grid vitals">
          <Gauge label={t("label.battery")} value={soc} unit="%" warnBelow={20} />
          <Gauge label={t("label.freshWater")} value={num(twin["fresh_water.level_pct"])} unit="%" warnBelow={15} />
          <Gauge label={t("label.cabin")} value={num(twin["cabin.temperature"])} unit="°C" min={-5} max={35} />
          <Gauge label={t("label.solar")} value={num(twin["solar.power"])} unit="W" min={0} max={600} />
        </div>
      </section>

      <section className="panel">
        <h2>{t("home.quickActions")}</h2>
        <div className="quick-grid">
          <QuickToggle
            icon="bulb"
            label={t("device.cabinLight")}
            state={lightOn ? t("common.on") : t("common.off")}
            on={lightOn}
            disabled={!light}
            onClick={() => sendIntent("light.cabin", lightOn ? "turn_off" : "turn_on")}
          />
          <QuickToggle
            icon="flame"
            label={t("device.dieselHeater")}
            state={heaterOn ? t("common.heating") : t("common.off")}
            on={heaterOn}
            disabled={!heater}
            onClick={() =>
              sendIntent("climate.diesel_heater", heaterOn ? "turn_off" : "turn_on")
            }
          />
          <QuickToggle
            icon="drop"
            label={t("device.waterPump")}
            state={pumpOn ? t("common.running") : t("common.off")}
            on={pumpOn}
            disabled={!pump}
            onClick={() => sendIntent("switch.water_pump", pumpOn ? "turn_off" : "turn_on")}
          />
        </div>
      </section>

      <Scenes />

      <section className="panel">
        <Companion notices={notices} />
      </section>
    </div>
  );
}
