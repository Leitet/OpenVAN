import { useState } from "react";
import { sendIntent, sendText } from "./api";
import { Gauge } from "./components/Gauge";
import { SignalSlider } from "./components/SignalSlider";
import { EventLog } from "./components/EventLog";
import { VanView } from "./components/VanView";
import { useVanState } from "./useVanState";

function num(v: unknown): number | undefined {
  return typeof v === "number" ? v : undefined;
}

export default function App() {
  const { entities, twin, log, connected } = useVanState();
  const [text, setText] = useState("");

  const light = entities["light.cabin"];
  const lightOn = light?.state === "on";
  const soc = num(twin["house_battery.soc"]);

  const toggleLight = () =>
    sendIntent("light.cabin", lightOn ? "turn_off" : "turn_on");

  const runText = (e: React.FormEvent) => {
    e.preventDefault();
    if (text.trim()) sendText(text.trim());
    setText("");
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <strong>OpenVan</strong> <span>Simulator</span>
        </div>
        <div className={"conn" + (connected ? " up" : " down")}>
          {connected ? "Core connected" : "Reconnecting…"}
        </div>
      </header>

      <main className="grid">
        <section className="panel twin">
          <h2>Digital twin</h2>
          <VanView
            lightOn={lightOn}
            soc={soc}
            cabinTemp={num(twin["cabin.temperature"])}
          />
        </section>

        <section className="panel gauges">
          <h2>Telemetry</h2>
          <div className="gauge-grid">
            <Gauge label="Battery" value={soc} unit="%" warnBelow={20} />
            <Gauge
              label="Voltage"
              value={num(twin["house_battery.voltage"])}
              unit="V"
              min={10}
              max={15}
            />
            <Gauge
              label="Solar"
              value={num(twin["solar.power"])}
              unit="W"
              min={0}
              max={600}
            />
            <Gauge
              label="Fresh water"
              value={num(twin["fresh_water.level_pct"])}
              unit="%"
              warnBelow={15}
            />
            <Gauge
              label="Cabin"
              value={num(twin["cabin.temperature"])}
              unit="°C"
              min={-5}
              max={35}
            />
            <Gauge
              label="Outside"
              value={num(twin["outside.temperature"])}
              unit="°C"
              min={-20}
              max={40}
            />
          </div>
        </section>

        <section className="panel controls">
          <h2>Van controls</h2>
          <button
            className={"toggle" + (lightOn ? " on" : "")}
            onClick={toggleLight}
            disabled={!light}
          >
            {lightOn ? "Cabin light: ON" : "Cabin light: OFF"}
          </button>
          <form className="text-cmd" onSubmit={runText}>
            <input
              placeholder='Try "turn on the cabin light"'
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <button type="submit">Send</button>
          </form>
        </section>

        <section className="panel inject">
          <h2>Inject sensors (play the physical van)</h2>
          <SignalSlider label="Battery SoC" signalKey="house_battery.soc" value={soc} min={0} max={100} unit="%" />
          <SignalSlider label="Solar power" signalKey="solar.power" value={num(twin["solar.power"])} min={0} max={600} step={10} unit="W" />
          <SignalSlider label="Fresh water" signalKey="fresh_water.level_pct" value={num(twin["fresh_water.level_pct"])} min={0} max={100} unit="%" />
          <SignalSlider label="Cabin temp" signalKey="cabin.temperature" value={num(twin["cabin.temperature"])} min={-5} max={35} step={0.5} unit="°C" />
          <SignalSlider label="Outside temp" signalKey="outside.temperature" value={num(twin["outside.temperature"])} min={-20} max={40} step={0.5} unit="°C" />
          <p className="hint">
            Drop the battery below 10% and try the light — Core's safety layer
            will refuse the non-essential load.
          </p>
        </section>

        <section className="panel">
          <EventLog log={log} />
        </section>
      </main>
    </div>
  );
}
