# OpenVan

**An open, AI-first and offline-first operating system for camper vans.**

> Home Assistant knows your home. OpenVan understands your journey.

OpenVan is more than a dashboard for batteries and lights. It is an intelligent
travel companion that unifies automation, energy, climate, navigation and
assistance into one cohesive platform — and it works without internet.

It is designed to *extend* Home Assistant, not replace it: when the van comes
home, it becomes part of the home's automation.

---

## Status

Early skeleton. What works today, end-to-end and tested:

- **OpenVan Core** (Python) — async event bus, entity model, plugin system,
  safety layer, LLM-agnostic intent resolver, local HTTP + WebSocket API.
- **Digital twin + simulator** (React) — there is no physical van yet, so we
  develop against a web-based twin: live gauges, sensor-injection sliders, van
  controls, and an activity/safety log.
- **Reference plugins** — `battery_monitor` (sensors), `cabin_light`,
  `diesel_heater` and `water_system` (safety-checked actuators).
- **Environment simulation** — the twin evolves over time (heater warms the
  cabin, cabin loses heat outside, pump moves water fresh → grey).
- **Local, model-agnostic AI assistant** — natural-language commands resolve to
  safety-checked intents via a local LLM (Ollama), with an offline rule-based
  fallback so it works with no model at all.

See [the vision & rules in CLAUDE.md](CLAUDE.md) and the
[plugin guide](docs/PLUGINS.md).

---

## Quick start

Two terminals.

**1 · Core**

```bash
cd core
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                 # verify (should be all green)
python -m openvan_core # http://127.0.0.1:8000
```

**2 · Simulator**

```bash
cd simulator
npm install
npm run dev            # http://localhost:5173
```

Open the simulator. You'll see the van twin, live telemetry, and controls. Try:

- Toggle the cabin light — watch it light up in the twin and log as allowed.
- Drag **Battery SoC** below 10%, toggle the light again — Core's safety layer
  refuses the non-essential load, and the log shows why.
- Type *"turn on the cabin light"* — the offline intent resolver handles it.

### Optional: local AI assistant

Core works fully without it, but for natural-language commands install
[Ollama](https://ollama.com) and pull a small model:

```bash
ollama pull llama3.2      # then Core auto-detects it on startup
```

With Ollama running, the header shows **AI: llama3.2** and you can type things
like *"it's freezing, warm it up"* — the model proposes an intent, and Core's
safety layer still vets it. Without Ollama, the header shows **AI: offline
rules** and simple phrasings still work. Configure with `OPENVAN_LLM_MODEL`,
`OPENVAN_LLM_URL`, or disable entirely with `OPENVAN_AI=0`.

---

## Architecture in one picture

```
Simulator (React)  ──HTTP/WebSocket──►  OpenVan Core (Python)  ──Backend──►  VanTwin
   digital twin UI                       bus · safety · plugins            (sim hardware)
```

Plugins read/write hardware only through a `Backend`. Today that's `SimBackend`
(the twin); real backends (Victron, Modbus, CAN, MQTT…) implement the same
interface later — so **every feature runs in the simulator by construction**.

Full details, data flow, and the contributor rules are in [CLAUDE.md](CLAUDE.md).

---

## Design principles

- **AI-first** — the AI proposes intents; Core validates them. Voice/text/app/
  dashboard, your choice of local, cloud, or hybrid model.
- **Offline-first** — lighting, heating, energy, water and automation never
  depend on the internet. Cloud only enhances (weather, maps, cloud AI).
- **Safety-first** — no model ever drives hardware directly.
- **Open** — own your data, choose your hardware, choose your AI. Plugin
  architecture for easy extension.

## Roadmap

Planned integrations: Victron, MQTT, Matter, ESPHome, ESP32, Shelly, CAN Bus,
OBD-II, diesel heaters, Starlink, Home Assistant. Plus travel memory (a living
journal of your journeys) and context-aware assistance.

## License

TBD.
