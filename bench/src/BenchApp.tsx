import { useCallback, useEffect, useState } from "react";
import {
  injectSignal,
  getWeather,
  refreshWeather,
  simulateWeather,
  getSettings,
  saveSettings,
  addCamera,
  removeCamera,
  getIntegrations,
  setIntegration,
} from "@shared/api";
import type { Weather, IntegrationInfo } from "@shared/types";
import { useVanState } from "@shared/useVanState";
import { SignalSlider } from "./components/SignalSlider";
import { VanView } from "./components/VanView";
import { TurboDash } from "./components/TurboDash";

function num(v: unknown): number | undefined {
  return typeof v === "number" ? v : undefined;
}

const RATES: [string, number][] = [
  ["Pause", 0],
  ["1×", 1],
  ["60×", 60],
  ["1800×", 1800],
];
const JUMPS: [string, number][] = [
  ["🌅 Dawn", 5],
  ["☀ Day", 12],
  ["🌆 Dusk", 19],
  ["🌙 Night", 0],
];

// Drives the simulated clock (clock.epoch as UTC seconds) + rate. The sim derives
// the sun and day/night phase, which the product UI reads.
function TimePanel({ twin }: { twin: Record<string, unknown> }) {
  const epoch = num(twin["clock.epoch"]) ?? 0;
  const rate = num(twin["clock.rate"]) ?? 1;
  const phase = String(twin["environment.phase"] ?? "—");
  const elev = num(twin["sun.elevation_deg"]);
  const inputValue = epoch ? new Date(epoch * 1000).toISOString().slice(0, 16) : "";
  const dayStart = Math.floor(epoch / 86400) * 86400;

  return (
    <div className="time-panel">
      <div className="time-readout">
        <strong>{epoch ? new Date(epoch * 1000).toUTCString() : "—"}</strong>
        <span className={"phase phase-" + phase}>
          {phase}
          {elev !== undefined ? ` · sun ${elev.toFixed(0)}°` : ""}
        </span>
      </div>
      <input
        type="datetime-local"
        value={inputValue}
        onChange={(e) => {
          const t = Date.parse(e.target.value + ":00Z");
          if (!Number.isNaN(t)) injectSignal("clock.epoch", t / 1000);
        }}
      />
      <div className="time-row">
        <span className="time-lbl">Rate</span>
        {RATES.map(([label, r]) => (
          <button
            key={label}
            className={"chip" + (rate === r ? " on" : "")}
            onClick={() => injectSignal("clock.rate", r)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="time-row">
        <span className="time-lbl">Jump</span>
        {JUMPS.map(([label, h]) => (
          <button
            key={label}
            className="chip"
            onClick={() => injectSignal("clock.epoch", dayStart + h * 3600)}
          >
            {label}
          </button>
        ))}
      </div>
      <p className="note">
        Set a rate above 1× to watch a day go by; the camera feeds switch to night
        vision after dark.
      </p>
    </div>
  );
}

// Fire a batch of raw signals at Core — the bench's whole job.
function apply(signals: Array<[string, number | boolean]>) {
  for (const [key, value] of signals) injectSignal(key, value);
}

const SCENARIOS: Array<{ label: string; signals: Array<[string, number | boolean]> }> = [
  { label: "Critical battery", signals: [["house_battery.soc", 8]] },
  { label: "Full sun", signals: [["solar.power", 550]] },
  { label: "Freezing night", signals: [["outside.temperature", -8], ["solar.power", 0]] },
  { label: "Empty fresh tank", signals: [["fresh_water.level_pct", 2]] },
  { label: "CO alarm", signals: [["air.co_ppm", 120]] },
  { label: "Gas leak", signals: [["air.lpg_pct_lel", 25]] },
  { label: "Condensation", signals: [["cabin.humidity_pct", 80], ["outside.temperature", 4]] },
  { label: "Clear the air", signals: [["air.co_ppm", 0], ["air.lpg_pct_lel", 0], ["air.co2_ppm", 600], ["air.smoke", false]] },
  { label: "Low bridge ahead", signals: [["road.max_height_m", 2.6]] },
  { label: "Weight-limited bridge", signals: [["road.max_weight_t", 3.0]] },
  { label: "Clear road", signals: [["road.max_height_m", 0], ["road.max_weight_t", 0]] },
];

function fmt(v: number | boolean | string): string {
  if (typeof v === "boolean") return v ? "ON" : "OFF";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  return String(v);
}

const LOCATIONS = ["rear", "cabin", "door", "awning"];
const CONNECTIONS = ["wired", "wifi", "4g"];

function CameraAdder() {
  const [id, setId] = useState("");
  const [label, setLabel] = useState("");
  const [location, setLocation] = useState("cabin");
  const [connection, setConnection] = useState("wifi");

  const add = async () => {
    const cid = id.trim().toLowerCase().replace(/[^a-z0-9_]/g, "");
    if (!cid) return;
    await addCamera({ id: cid, label: label.trim() || cid, location, connection });
    setId("");
    setLabel("");
  };

  return (
    <div className="cam-add">
      <input placeholder="id" value={id} onChange={(e) => setId(e.target.value)} />
      <input placeholder="name" value={label} onChange={(e) => setLabel(e.target.value)} />
      <select value={location} onChange={(e) => setLocation(e.target.value)}>
        {LOCATIONS.map((l) => (
          <option key={l} value={l}>
            {l}
          </option>
        ))}
      </select>
      <select value={connection} onChange={(e) => setConnection(e.target.value)}>
        {CONNECTIONS.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
      <button className="chip on" onClick={add}>
        + add
      </button>
    </div>
  );
}

// Integration drivers, as the bench sees them. Enabling one turns its driver on
// in Core; in sim mode the driver injects the raw signals real hardware would emit
// (Rule 1) — visible immediately in the Signal inspector below. A few integrations
// also *read* bench inputs (shore plugged in, inverter running), toggled here.
function IntegrationsPanel({ twin }: { twin: Record<string, unknown> }) {
  const [items, setItems] = useState<IntegrationInfo[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    getIntegrations().then(setItems);
  }, []);

  const toggle = async (id: string, enabled: boolean) => {
    setBusy(id);
    try {
      setItems(await setIntegration(id, enabled));
    } finally {
      setBusy(null);
    }
  };

  // Only the installed set — the full searchable library lives in the product UI.
  const installed = items.filter((it) => it.installed);

  return (
    <>
      <div className="bench-integrations">
        {installed.length === 0 ? (
          <p className="note">No integrations installed.</p>
        ) : (
          installed.map((it) => (
            <div key={it.id} className={"bench-int-row" + (it.enabled ? " on" : "")}>
              <button
                className={"toggle" + (it.enabled ? " on" : "")}
                disabled={busy === it.id || it.builtin}
                title={it.builtin ? "Built-in — always on" : "Remove"}
                onClick={() => toggle(it.id, !it.enabled)}
              >
                {it.builtin ? "built-in" : "remove"}
              </button>
              <div className="bench-int-meta">
                <strong>{it.name}</strong>
                <span className="note">
                  {it.status} · {it.transports.join(", ")} · safety {it.safety_class}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
      <p className="note">
        Installed integrations only — add more from the product UI (Settings →
        Integrations → Browse library).
      </p>
      <h3>Device inputs (what drivers read)</h3>
      <button
        className={"toggle" + (twin["shore.connected"] ? " on" : "")}
        onClick={() => injectSignal("shore.connected", !twin["shore.connected"])}
      >
        Shore power {twin["shore.connected"] ? "connected" : "unplugged"}
      </button>
      <button
        className={"toggle" + (twin["inverter.on"] ? " on" : "")}
        onClick={() => injectSignal("inverter.on", !twin["inverter.on"])}
      >
        Inverter {twin["inverter.on"] ? "on" : "off"}
      </button>
      <SignalSlider
        label="Inverter AC load"
        signalKey="inverter.ac_load"
        value={num(twin["inverter.ac_load"])}
        min={0}
        max={2000}
        step={50}
        unit=" W"
      />
      <button
        className={"toggle" + (twin["home_assistant.van_home"] ? " on" : "")}
        onClick={() => injectSignal("home_assistant.van_home", !twin["home_assistant.van_home"])}
      >
        Van at home {twin["home_assistant.van_home"] ? "yes" : "no"}
      </button>
      <p className="note">
        Enable an integration, then watch its normalised signals appear below. On a
        real van these come from the actual device over its protocol.
      </p>
    </>
  );
}

export function BenchApp() {
  const { twin, connected, entities } = useVanState();
  const [wx, setWx] = useState<Weather>({});
  const [simulate, setSimulate] = useState<boolean | null>(null);

  const loadWx = useCallback(async () => setWx(await getWeather()), []);

  useEffect(() => {
    loadWx();
    getSettings().then((s) => setSimulate(s.simulate));
  }, [loadWx]);

  const toggleSim = async () => {
    const next = !simulate;
    setSimulate(next);
    const s = await saveSettings({ simulate: next });
    setSimulate(s.simulate);
  };

  const ignition = Boolean(twin["vehicle.ignition"]);
  const twinKeys = Object.keys(twin).sort();

  return (
    <div className="bench">
      <header className="bench-bar">
        <div className="bench-title">
          <span className="warn-chip">⚠ HARDWARE SIMULATOR</span>
          <span className="bench-name">OpenVan Bench</span>
          <span className="bench-sub">
            dev stand-in for the physical van — signals injected here are what Core
            would read from real sensors
          </span>
        </div>
        <div className="bench-status">
          <a className="ext-link" href="http://localhost:5173" target="_blank" rel="noreferrer">
            Product UI ↗
          </a>
          <span className={"conn" + (connected ? " up" : " down")}>
            {connected ? "Core connected" : "Reconnecting…"}
          </span>
        </div>
      </header>

      <main className="bench-grid">
        <section className="card">
          <h2>Time</h2>
          <TimePanel twin={twin} />
        </section>

        <section className="card">
          <h2>Signals</h2>
          <SignalSlider label="Battery SoC" signalKey="house_battery.soc" value={num(twin["house_battery.soc"])} min={0} max={100} unit="%" />
          <SignalSlider label="Solar power" signalKey="solar.power" value={num(twin["solar.power"])} min={0} max={600} step={10} unit="W" />
          <SignalSlider label="Fresh water" signalKey="fresh_water.level_pct" value={num(twin["fresh_water.level_pct"])} min={0} max={100} unit="%" />
          <SignalSlider label="Outside temp" signalKey="outside.temperature" value={num(twin["outside.temperature"])} min={-20} max={40} step={0.5} unit="°C" />
          <SignalSlider label="Diesel fuel" signalKey="diesel_tank.level_pct" value={num(twin["diesel_tank.level_pct"])} min={0} max={100} unit="%" />
          <SignalSlider label="Propane" signalKey="propane.level_pct" value={num(twin["propane.level_pct"])} min={0} max={100} unit="%" />
          <SignalSlider label="Fridge temp" signalKey="fridge.temp_c" value={num(twin["fridge.temp_c"])} min={-5} max={20} step={0.5} unit="°C" />
          <button
            className={"toggle" + (twin["fridge.door_open"] ? " on" : "")}
            onClick={() => injectSignal("fridge.door_open", !twin["fridge.door_open"])}
          >
            {twin["fridge.door_open"] ? "Fridge door: OPEN" : "Fridge door: closed"}
          </button>
          <p className="note">
            Cabin temperature is <em>derived</em> by Core's thermal model, not injected —
            set the outside temp cold and turn on the heater from the product UI to
            watch the cabin respond.
          </p>
        </section>

        <section className="card span-2 turbo-card">
          <h2>Drive — Turbo Dash 🏁</h2>
          <TurboDash
            speed={num(twin["vehicle.speed_kmh"]) ?? 0}
            ignition={ignition}
            heading={num(twin["vehicle.heading"]) ?? 0}
            onSignal={injectSignal}
          />
          <p className="note">
            Turn the key, hit the gas, steer with the wheel (or ← →). It's a toy —
            but it drives the real twin: throttle sets <code>vehicle.speed_kmh</code>,
            the wheel integrates <code>vehicle.heading</code>, so the van dead-reckons
            and the product-UI map traces your route as you pass cars.
          </p>
        </section>

        <section className="card">
          <h2>Air &amp; Safety</h2>
          <SignalSlider label="Carbon monoxide" signalKey="air.co_ppm" value={num(twin["air.co_ppm"])} min={0} max={200} step={5} unit=" ppm" />
          <SignalSlider label="LPG / propane" signalKey="air.lpg_pct_lel" value={num(twin["air.lpg_pct_lel"])} min={0} max={100} unit=" %LEL" />
          <SignalSlider label="CO₂" signalKey="air.co2_ppm" value={num(twin["air.co2_ppm"])} min={400} max={3000} step={50} unit=" ppm" />
          <SignalSlider label="Cabin humidity" signalKey="cabin.humidity_pct" value={num(twin["cabin.humidity_pct"])} min={0} max={100} unit="%" />
          <button
            className={"toggle" + (twin["air.smoke"] ? " on" : "")}
            onClick={() => injectSignal("air.smoke", !twin["air.smoke"])}
          >
            {twin["air.smoke"] ? "Smoke: DETECTED" : "Smoke: clear"}
          </button>
          <button
            className={"toggle" + (twin["security.door_open"] ? " on" : "")}
            onClick={() => injectSignal("security.door_open", !twin["security.door_open"])}
          >
            {twin["security.door_open"] ? "Door: OPEN" : "Door: closed"}
          </button>
          <button
            className={"toggle" + (twin["security.motion"] ? " on" : "")}
            onClick={() => injectSignal("security.motion", !twin["security.motion"])}
          >
            {twin["security.motion"] ? "Motion: DETECTED" : "Motion: none"}
          </button>
          <p className="note">
            CO/gas/smoke trip deterministic edge alarms in Core (no model in the danger
            path). Condensation fires from humidity vs. the dew point on cold walls.
          </p>
        </section>

        <section className="card">
          <h2>Cameras</h2>
          {Object.values(entities)
            .filter((e) => e.domain === "camera")
            .map((cam) => {
              const id = cam.entity_id.split(".")[1];
              return (
                <div className="cam-row" key={id}>
                  <span className="cam-row-label">{cam.name}</span>
                  <button
                    className={"chip" + (twin[`camera.${id}.online`] ? " on" : "")}
                    onClick={() => injectSignal(`camera.${id}.online`, !twin[`camera.${id}.online`])}
                  >
                    {twin[`camera.${id}.online`] ? "online" : "offline"}
                  </button>
                  <button
                    className={"chip" + (twin[`camera.${id}.motion`] ? " warn" : "")}
                    onClick={() => injectSignal(`camera.${id}.motion`, !twin[`camera.${id}.motion`])}
                  >
                    motion
                  </button>
                  <button
                    className={"chip" + (twin[`camera.${id}.recording`] ? " rec" : "")}
                    onClick={() => injectSignal(`camera.${id}.recording`, !twin[`camera.${id}.recording`])}
                  >
                    rec
                  </button>
                  <button className="chip danger" title="Remove" onClick={() => removeCamera(id)}>
                    ✕
                  </button>
                </div>
              );
            })}
          <CameraAdder />
          <p className="note">Add/remove cameras here; motion on any while Away mode is armed trips the intrusion alarm.</p>
        </section>

        <section className="card">
          <h2>Leveling</h2>
          <SignalSlider label="Pitch (nose up +)" signalKey="imu.pitch_deg" value={num(twin["imu.pitch_deg"])} min={-8} max={8} step={0.1} unit="°" />
          <SignalSlider label="Roll (right low +)" signalKey="imu.roll_deg" value={num(twin["imu.roll_deg"])} min={-8} max={8} step={0.1} unit="°" />
          <p className="note">Parked + off level makes the van suggest which ramp to use, on the Journey tab.</p>
        </section>

        <section className="card">
          <h2>Road ahead</h2>
          <SignalSlider label="Max height (0 = none)" signalKey="road.max_height_m" value={num(twin["road.max_height_m"])} min={0} max={5} step={0.1} unit=" m" />
          <SignalSlider label="Max weight (0 = none)" signalKey="road.max_weight_t" value={num(twin["road.max_weight_t"])} min={0} max={40} step={0.5} unit=" t" />
          <p className="note">
            Checked against the vehicle profile (Settings → Vehicle). Set a limit
            below the van's height/weight to trigger a routing warning. On a real
            van these come from OSM maxheight/maxweight on the road ahead.
          </p>
        </section>

        <section className="card">
          <h2>Scenarios</h2>
          <div className="scenario-grid">
            {SCENARIOS.map((s) => (
              <button key={s.label} className="scenario" onClick={() => apply(s.signals)}>
                {s.label}
              </button>
            ))}
          </div>

          <h3>Weather</h3>
          <div className="wx-row">
            <span className="wx-src">
              {wx.source === "simulated" ? "simulated" : wx.online ? "live" : wx.current ? "cached" : "—"}
              {wx.current?.temp_c != null ? ` · ${wx.current.temp_c.toFixed(0)}°C` : ""}
            </span>
            <button className="mini" onClick={() => refreshWeather().then(loadWx)}>Refresh</button>
            <button className="mini" onClick={() => simulateWeather("rain").then(loadWx)}>Rain</button>
            <button className="mini" onClick={() => simulateWeather("clear").then(loadWx)}>Clear</button>
          </div>

          <h3>Environment physics</h3>
          <label className="sim-toggle">
            <input type="checkbox" checked={!!simulate} disabled={simulate === null} onChange={toggleSim} />
            Run thermal &amp; water simulation
          </label>
          <p className="note">Off = the twin holds still, for testing against fixed state.</p>
        </section>

        <section className="card">
          <h2>Digital twin</h2>
          <div className="twin-view">
            <VanView
              lightOn={Boolean(twin["cabin_light.on"])}
              heaterOn={Boolean(twin["diesel_heater.on"])}
              soc={num(twin["house_battery.soc"])}
              cabinTemp={num(twin["cabin.temperature"])}
            />
          </div>
          <p className="note">
            The van as Core sees it right now — driven entirely by the signals
            above. On a real van this comes from actual hardware.
          </p>
        </section>

        <section className="card">
          <h2>Integrations</h2>
          <IntegrationsPanel twin={twin} />
        </section>

        <section className="card span-2">
          <h2>Signal inspector</h2>
          <div className="signal-table">
            {twinKeys.length === 0 ? (
              <span className="note">No signals yet — waiting for Core…</span>
            ) : (
              twinKeys.map((k) => (
                <div key={k} className="signal-row">
                  <span className="sig-k">{k}</span>
                  <span className="sig-v">{fmt(twin[k])}</span>
                </div>
              ))
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
