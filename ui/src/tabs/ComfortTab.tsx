import { sendIntent } from "@shared/api";
import { useVan, num } from "../state";
import { Gauge } from "../components/Gauge";
import { HeaterControl } from "../components/HeaterControl";
import { QuickToggle } from "../components/QuickToggle";

export function ComfortTab() {
  const { entities, twin } = useVan();
  const heater = entities["climate.diesel_heater"];
  const pump = entities["switch.water_pump"];
  const pumpOn = pump?.state === "on";

  return (
    <div className="tab-grid comfort">
      <section className="panel">
        <h2>Climate</h2>
        <div className="gauge-grid">
          <Gauge label="Cabin" value={num(twin["cabin.temperature"])} unit="°C" min={-5} max={35} />
          <Gauge label="Outside" value={num(twin["outside.temperature"])} unit="°C" min={-20} max={40} />
        </div>
        <HeaterControl entity={heater} />
      </section>

      <section className="panel">
        <h2>Water</h2>
        <div className="gauge-grid">
          <Gauge label="Fresh water" value={num(twin["fresh_water.level_pct"])} unit="%" warnBelow={15} />
          <Gauge label="Grey water" value={num(twin["grey_water.level_pct"])} unit="%" />
        </div>
        <QuickToggle
          icon="drop"
          label="Water pump"
          state={pumpOn ? "Running" : "Off"}
          on={pumpOn}
          disabled={!pump}
          onClick={() => sendIntent("switch.water_pump", pumpOn ? "turn_off" : "turn_on")}
        />
      </section>
    </div>
  );
}
