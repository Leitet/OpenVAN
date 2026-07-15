import { sendIntent } from "@shared/api";
import { useVan, num } from "../state";
import { Gauge } from "../components/Gauge";
import { QuickToggle } from "../components/QuickToggle";
import { Companion } from "../components/Companion";

export function HomeTab() {
  const { entities, twin, notices } = useVan();
  const soc = num(twin["house_battery.soc"]);
  const light = entities["light.cabin"];
  const lightOn = light?.state === "on";
  const heater = entities["climate.diesel_heater"];
  const heaterOn = heater?.state === "heating";
  const pump = entities["switch.water_pump"];
  const pumpOn = pump?.state === "on";

  return (
    <div className="tab-grid home">
      <section className="panel">
        <h2>Vitals</h2>
        <div className="gauge-grid vitals">
          <Gauge label="Battery" value={soc} unit="%" warnBelow={20} />
          <Gauge label="Fresh water" value={num(twin["fresh_water.level_pct"])} unit="%" warnBelow={15} />
          <Gauge label="Cabin" value={num(twin["cabin.temperature"])} unit="°C" min={-5} max={35} />
          <Gauge label="Solar" value={num(twin["solar.power"])} unit="W" min={0} max={600} />
        </div>
      </section>

      <section className="panel">
        <h2>Quick actions</h2>
        <div className="quick-grid">
          <QuickToggle
            icon="bulb"
            label="Cabin light"
            state={lightOn ? "On" : "Off"}
            on={lightOn}
            disabled={!light}
            onClick={() => sendIntent("light.cabin", lightOn ? "turn_off" : "turn_on")}
          />
          <QuickToggle
            icon="flame"
            label="Diesel heater"
            state={heaterOn ? "Heating" : "Off"}
            on={heaterOn}
            disabled={!heater}
            onClick={() =>
              sendIntent("climate.diesel_heater", heaterOn ? "turn_off" : "turn_on")
            }
          />
          <QuickToggle
            icon="drop"
            label="Water pump"
            state={pumpOn ? "Running" : "Off"}
            on={pumpOn}
            disabled={!pump}
            onClick={() => sendIntent("switch.water_pump", pumpOn ? "turn_off" : "turn_on")}
          />
        </div>
      </section>

      <section className="panel span2">
        <Companion notices={notices} />
      </section>
    </div>
  );
}
