import { useEffect, useState } from "react";
import { sendIntent, sendText } from "@shared/api";
import { Gauge } from "./components/Gauge";
import { EventLog } from "./components/EventLog";
import { HeaterControl } from "./components/HeaterControl";
import { Companion } from "./components/Companion";
import { AdminPanel } from "./components/AdminPanel";
import { Trends } from "./components/Trends";
import { Predictions } from "./components/Predictions";
import { Journey } from "./components/Journey";
import { Weather } from "./components/Weather";
import { Journal } from "./components/Journal";
import { VanView } from "./components/VanView";
import { useVanState } from "@shared/useVanState";

function num(v: unknown): number | undefined {
  return typeof v === "number" ? v : undefined;
}

export default function App() {
  const { entities, twin, log, assistant, notices, connected } = useVanState();
  const [text, setText] = useState("");
  const [view, setView] = useState<"dashboard" | "admin">("dashboard");

  // The whole UI themes to the active persona (design-system [data-theme]).
  useEffect(() => {
    document.documentElement.setAttribute(
      "data-theme",
      assistant.personality_id || "aurora",
    );
  }, [assistant.personality_id]);

  const light = entities["light.cabin"];
  const lightOn = light?.state === "on";
  const heater = entities["climate.diesel_heater"];
  const heaterOn = heater?.state === "heating";
  const pump = entities["switch.water_pump"];
  const pumpOn = pump?.state === "on";
  const soc = num(twin["house_battery.soc"]);

  const toggleLight = () =>
    sendIntent("light.cabin", lightOn ? "turn_off" : "turn_on");

  const togglePump = () =>
    sendIntent("switch.water_pump", pumpOn ? "turn_off" : "turn_on");

  const runText = (e: React.FormEvent) => {
    e.preventDefault();
    if (text.trim()) sendText(text.trim());
    setText("");
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <strong>OpenVan</strong> <span>OS</span>
          <nav className="tabs">
            <button
              className={view === "dashboard" ? "tab active" : "tab"}
              onClick={() => setView("dashboard")}
            >
              Dashboard
            </button>
            <button
              className={view === "admin" ? "tab active" : "tab"}
              onClick={() => setView("admin")}
            >
              Admin
            </button>
          </nav>
        </div>
        <div className="status">
          <span className={"conn" + (assistant.llm ? " up" : "")}>
            {(assistant.llm
              ? `AI: ${assistant.connectivity ?? ""} · ${assistant.model}`
              : "AI: offline rules") +
              (assistant.personality ? ` · ${assistant.personality}` : "")}
          </span>
          <span className={"conn" + (connected ? " up" : " down")}>
            {connected ? "Core connected" : "Reconnecting…"}
          </span>
        </div>
      </header>

      <main className="grid">
        {view === "admin" ? (
          <AdminPanel />
        ) : (
        <>
        <section className="panel span2">
          <Companion notices={notices} />
        </section>

        <section className="panel twin">
          <h2>Digital twin</h2>
          <VanView
            lightOn={lightOn}
            heaterOn={heaterOn}
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
              label="Grey water"
              value={num(twin["grey_water.level_pct"])}
              unit="%"
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
            <Gauge
              label="Diesel fuel"
              value={num(twin["diesel_tank.level_pct"])}
              unit="%"
              warnBelow={15}
            />
            <Gauge
              label="Heater draw"
              value={num(twin["diesel_heater.power"])}
              unit="W"
              min={0}
              max={120}
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
          <HeaterControl entity={heater} />
          <button
            className={"toggle" + (pumpOn ? " on" : "")}
            onClick={togglePump}
            disabled={!pump}
          >
            {pumpOn ? "Water pump: RUNNING" : "Water pump: OFF"}
          </button>
          <form className="text-cmd" onSubmit={runText}>
            <input
              placeholder={
                assistant.llm
                  ? 'Ask anything, e.g. "it\'s freezing, warm it up"'
                  : 'Try "turn on the cabin light"'
              }
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <button type="submit">Send</button>
          </form>
        </section>

        <Journey twin={twin} />

        <Journal />

        <Weather />

        <Trends />

        <Predictions />

        <section className="panel">
          <EventLog log={log} />
        </section>
        </>
        )}
      </main>
    </div>
  );
}
