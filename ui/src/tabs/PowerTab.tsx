import { useVan, num } from "../state";
import { Gauge } from "../components/Gauge";
import { Trends } from "../components/Trends";
import { Predictions } from "../components/Predictions";

export function PowerTab() {
  const { twin } = useVan();
  return (
    <div className="tab-grid power">
      <section className="panel">
        <h2>Energy</h2>
        <div className="gauge-grid">
          <Gauge label="Battery" value={num(twin["house_battery.soc"])} unit="%" warnBelow={20} />
          <Gauge label="Voltage" value={num(twin["house_battery.voltage"])} unit="V" min={10} max={15} />
          <Gauge label="Solar" value={num(twin["solar.power"])} unit="W" min={0} max={600} />
          <Gauge label="Heater draw" value={num(twin["diesel_heater.power"])} unit="W" min={0} max={120} />
        </div>
      </section>

      <Predictions />
      <Trends />
    </div>
  );
}
