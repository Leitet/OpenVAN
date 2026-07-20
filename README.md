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
- **Two web front-ends** (React) — a persona-themed **product UI** (the OpenVan
  OS: companion, digital twin, telemetry, controls, journey, journal, weather)
  and a separate **Hardware Bench** that stands in for the physical van by
  injecting raw sensor/vehicle signals. There is no real van yet, so the bench
  plays "physical world" while the product UI is exactly what ships.
- **Reference plugins** — `battery_monitor` (sensors), `cabin_light`,
  `diesel_heater` and `water_system` (safety-checked actuators).
- **Environment simulation** — the twin evolves over time (heater warms the
  cabin, cabin loses heat outside, pump moves water fresh → grey).
- **Local, model-agnostic AI assistant** — natural-language commands resolve to
  safety-checked intents via a local LLM (Ollama), with an offline rule-based
  fallback so it works with no model at all.

See [the vision & rules in CLAUDE.md](CLAUDE.md), the
[plugin guide](docs/PLUGINS.md) and the
[driver guide](docs/DRIVERS.md) — drivers are **self-contained**: one
directory, zero UI code, and an enabled integration shows up in the product
UI, the bench's signal browser and the telemetry automatically.

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

**2 · Front-ends**

Two apps share one workspace (a single `npm install` at the repo root). The
**product UI** is the OpenVan OS; the **Hardware Bench** is the dev stand-in for
the physical van. Each runs on its own port.

```bash
npm install            # installs both apps (run at the repo root)
npm run dev:ui         # product UI    -> http://localhost:5173
npm run dev:bench      # hardware bench -> http://localhost:5174  (separate terminal)
```

Open the **product UI** (5173): the van twin, live telemetry, controls, and the
companion. Open the **Hardware Bench** (5174) to play the physical world:

- On the bench, drag **Battery SoC** below 10%, then toggle the cabin light in
  the product UI — Core's safety layer refuses the non-essential load, and the
  log shows why.
- In the product UI, type *"turn on the cabin light"* — the offline intent
  resolver handles it; watch the twin light up.
- Use the bench **Scenarios** (critical battery, freezing night, start driving…)
  to jump the twin to a state, and the **Signal inspector** to see every raw
  value Core is reading.
- The product **Admin** tab chooses the AI model and persona; the bench owns the
  environment-simulation toggle.

### Optional: MCP server (control OpenVan from an AI assistant)

Expose OpenVan to an MCP client (Claude Desktop/Code, etc.) so an assistant can
read state and control the van — with parity to the REST API. It bridges to the
running Core over HTTP, so keep `python -m openvan_core` running.

```bash
pip install -e "./core[mcp]"    # adds the mcp dependency
openvan-mcp                     # stdio MCP server -> talks to http://127.0.0.1:8000
```

Point your MCP client at the `openvan-mcp` command (override the target with
`OPENVAN_API_URL`). Tools include `get_state`, `control_device`, `command`
(natural language), `briefing`, `notices`, `weather`, `predictions`,
`telemetry`, `journal`, `bookmark_spot`, `get_settings`/`update_settings`, and
`personalities`/`set_personality`. Device commands are still safety-checked by
Core, and the API key is never settable over MCP.

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

**Online (cloud) models** are optional and per-profile — set them in the Admin
tab or via env. Two providers: any OpenAI-compatible endpoint
(`OPENVAN_ONLINE_PROVIDER=openai`, `OPENVAN_ONLINE_URL`, `OPENVAN_ONLINE_MODEL`) or
Anthropic/Claude (`OPENVAN_ONLINE_PROVIDER=anthropic`, `OPENVAN_ONLINE_MODEL`,
e.g. `claude-opus-4-8`). The key comes from `OPENVAN_ONLINE_API_KEY` (or the Admin
UI, memory-only) and is never written to disk. To avoid re-typing it each restart,
copy `.env.example` to **`.env`** (gitignored) and put your key there — Core loads
it on startup:

```bash
cp .env.example .env      # then edit .env: OPENVAN_ONLINE_API_KEY=sk-…
```

---

## Architecture in one picture

```
Product UI    (React, :5173) ─┐
                              ├─HTTP/WebSocket─►  OpenVan Core (Python) ──Backend──► VanTwin
Hardware Bench (React, :5174) ─┘                   bus · safety · plugins          (sim hardware)
```

The **product UI** reads state and issues safety-checked intents — it is the
software that ships on the van. The **Hardware Bench** injects the raw signals a
real sensor/vehicle would emit. Plugins read/write hardware only through a
`Backend`: today that's `SimBackend` (the twin), driven by the bench; real
backends (Victron, Modbus, CAN, MQTT…) implement the same interface later and the
bench simply goes away — so **every feature runs against the twin by
construction**.

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
