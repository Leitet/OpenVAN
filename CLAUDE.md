# CLAUDE.md — OpenVan

Architecture, patterns and the rules every contributor (human or AI) must follow.
Read this before writing code.

---

## What OpenVan is

An **open, AI-first, offline-first operating system for camper vans**.

> Home Assistant knows your home. OpenVan understands your journey.

OpenVan is not a replacement for Home Assistant — it is a natural extension of
it for the *vehicle* ecosystem. When the van comes home, it becomes part of the
home's automation.

Three core values guide every decision:

- **Smart** — AI helps people make better decisions.
- **Pleasant** — a helpful companion, not an industrial control panel.
- **Open** — users own their data, choose their hardware, choose their AI.

---

## The non-negotiable rules

### RULE 1 — Every feature must work against the twin

There is **no physical van yet**. We develop against a digital twin driven by two
web front-ends: the [**product UI**](ui/) (`ui/`, the OpenVan OS — how a real
user sees and controls the van) and the [**Hardware Bench**](bench/) (`bench/`,
the dev stand-in that injects the raw signals a real sensor/vehicle would emit).

> **When you add a feature, you add both its bench support (inject raw signals)
> and its product-UI surface (display/control) in the same change.**
> A plugin that cannot be exercised from the bench is not done.

Concretely, a new plugin must:

1. Read/write hardware **only** through a `Backend` (never touch hardware
   directly), so it runs against the simulated `VanTwin` out of the box.
2. Expose its raw signals so the **bench** can inject sensor values and observe
   actuator effects (add a `SignalSlider`/scenario to `bench/` when introducing
   new signal keys), and surface the result in the **product UI**.
3. Ship a test in `core/tests/` proving its behaviour against the twin.

This is not busywork — it is what keeps the AI feedback loop fast: change → run
Core → drive it from the bench (or a test) → see the result in the product UI →
adjust.

### RULE 2 — The AI never controls hardware directly

The AI only proposes an **`Intent`**. OpenVan Core validates every intent through
the **safety layer** (battery state, vehicle status, safety rules, environmental
constraints) before anything acts. Never add a code path that lets a model call
an actuator without going through `Hub.execute_intent` → `SafetyValidator`.

### RULE 3 — Offline-first

Core functionality (lighting, heating, battery, water, automation, local voice)
must work with **no internet**. Cloud is an *enhancement* (weather, cloud AI,
remote access, maps), never a dependency of the core control path.

### RULE 4 — Model-agnostic

Users choose their AI: local LLM, cloud LLM, or hybrid. `llm.py` has three clients
behind one `LLMClient` interface — `OllamaClient` (offline) and, for online, either
`OpenAICompatibleClient` (any OpenAI-compatible endpoint) or `AnthropicClient`
(Claude Messages API), selected by `online_provider`. All are raw-httpx, no vendor
SDKs, to keep the edge runtime small. A `ModelRouter` picks the effective client
from a **single global connectivity mode** (`Config.connectivity`: `offline` =
local Ollama, `online` = the configured cloud provider), falling back to the other
connectivity if the preferred one isn't reachable. Connectivity is **not** a
property of the personality — voice and model are fully orthogonal, and every
personality runs under whichever mode is active. It **always** falls back to the
offline rule-based resolver, so text commands work with no model at all — never
make the assistant a hard requirement.

---

## Architecture

```
   Product UI (React, :5173)   ── the OpenVan OS (ships on the van)
   Hardware Bench (React, :5174) ── dev stand-in: injects raw signals
              │  HTTP + WebSocket   (both share shared/: api client, types, WS hook)
              ▼
        ┌───────────────────────────── OpenVan Core (Python) ─────────────────┐
        │  api.py        FastAPI + WebSocket (local only)                      │
        │  hub.py        entity registry · routes intents · calls safety       │
        │  safety.py     SafetyValidator + rules (allow / deny / modify)       │
        │  intents.py    Intent + IntentResolver (LLM-agnostic seam)           │
        │  plugins.py    Plugin base + directory-based PluginManager           │
        │  entities.py   semantic, HA-style entities                           │
        │  events.py     async pub/sub EventBus (the spine)                    │
        │  backends.py   Backend seam:  SimBackend  ──▶  VanTwin               │
        │  twin.py       VanTwin: raw simulated hardware signals               │
        └─────────────────────────────────────────────────────────────────────┘
              ▲
              │ Backend interface (read / write / watch)
        ┌─────┴───────────────┐
        │  plugins/           │   battery_monitor · cabin_light · (your plugin)
        └─────────────────────┘
```

### Two layers, one seam

- **Twin signals** (`twin.py`) are the *raw hardware* reality — `house_battery.soc`,
  `cabin_light.on`. In simulation these are driven by the simulator; on a real
  van they come from actual devices.
- **Entities** (`entities.py`) are OpenVan's *semantic* model — `sensor.house_battery_soc`
  with a unit and friendly name, `light.cabin` with commands.
- Plugins bridge the two, and they do it **only** through a `Backend`
  (`backends.py`). Today the only backend is `SimBackend` (maps to `VanTwin`).
  A real deployment adds `VictronBackend`, `ModbusBackend`, `CanBackend`, … that
  implement the same `read` / `write` / `watch` interface. **This seam is why
  Rule 1 is cheap.**

### Proactive companion (`notices.py`, `companion.py`)

OpenVan speaks up before being asked. `Advisor`s are deterministic, offline-first
threshold checks over live state (low fresh water, grey tank full, battery
runtime, low diesel); the `AdvisorEngine` is edge-triggered — it emits
`notice.created` when a condition starts and `notice.cleared` when it stops, so
the companion never nags every tick. `Companion` composes a warm briefing from the
same facts: LLM-phrased when a model is available, templated otherwise (Rule 3).
Like the intent path, the AI only rewords facts we give it — it invents nothing
and controls nothing. New advisors: add an `Advisor` subclass to `default_advisors`.

### Travel memory (`memory.py`)

A living journal. `TravelMemory` auto-logs *stays*: when the van parks (ignition
off / stopped past a dwell time) it opens a stay at the current GPS, capturing
weather + battery; driving off closes it with duration and energy used (solar Wh
from telemetry). Users add notes, name places, or bookmark the current spot
instantly. Local SQLite (`data/journal.db`), surfaced to the companion for recall
("remember that lake?"). API: `/api/memory/*`.

### Weather (`weather.py`)

Location-aware, offline-first. `WeatherService` fetches the forecast for the
van's current GPS (from the vehicle plugin) via **open-meteo** (keyless), caches
it to `data/weather.json`, and serves the last-known forecast when offline (cloud
enhances, never required). Feeds the `RainSoon` advisor, the companion briefing
("rain expected in an hour"), and the simulator's weather panel. A `simulate()`
path injects a synthetic forecast so the rain behaviour works offline/in tests.

### Telemetry (`telemetry.py`)

Every numeric twin signal is recorded to a local **SQLite** time-series
(`data/telemetry.db`, stdlib — no dependency, offline-first). `TelemetryRecorder`
subscribes to `twin.signal_changed`, so **any signal a new plugin introduces is
captured automatically** — no wiring needed. `TelemetryStore` offers `series`
(with read-time bucket downsampling), `rate_per_hour` (trends), and retention
`prune`. All DB access runs off the loop via `asyncio.to_thread`. This history
powers the simulator's sparklines (`/api/telemetry/series`) and feeds the
companion real drain-rate trends, not just instantaneous readings.

### Environment simulation (`simulation.py`)

The twin holds state; `VanSimulation` makes it *evolve* — the heater warms the
cabin toward its setpoint, the cabin loses heat to the outside, the pump moves
water fresh → grey. This is **environment physics, not a feature**, so it lives in
the simulation layer (alongside `SimBackend`), not in a plugin. It runs only in
sim mode (`Config.simulate`); a real van gets these values from sensors. Values
a plugin *owns as an actuator* (e.g. `diesel_heater.on`) are written by the
plugin; values the *world* determines (e.g. `cabin.temperature`) are the
simulation's. Its constants are illustrative — measure a real van before shipping.

### Data flow

- Sensor: the **bench** injects `house_battery.soc` → `VanTwin` emits
  `twin.signal_changed` → `battery_monitor` updates `sensor.house_battery_soc` →
  WebSocket → the **product UI** gauge moves.
- Command: the product UI / AI sends an `Intent` → `Hub.execute_intent` → `SafetyValidator`
  → plugin handler writes the actuator signal via `Backend` → twin updates →
  the product UI reflects it. Every evaluation emits `intent.evaluated` (shown in the
  simulator's activity/safety log).

---

## Plugin structure

Plugins live under [`plugins/`](plugins/), one package per plugin. Each declares
a **domain** and one or more **categories** so features group cleanly:

| Category   | Examples                                   |
| ---------- | ------------------------------------------ |
| `energy`   | battery monitor, solar, shore power, inverter |
| `lighting` | cabin lights, awning light, reading lamps  |
| `climate`  | diesel heater, fan, A/C, thermostat        |
| `water`    | fresh/grey tanks, pump, water heater       |
| `sensors`  | temperature, humidity, GPS, gas, motion    |
| `vehicle`  | OBD-II, CAN bus, doors, ignition           |
| `connectivity` | Starlink, LTE, Wi-Fi                   |

A plugin is a subclass of `openvan_core.Plugin` that self-registers. See
[docs/PLUGINS.md](docs/PLUGINS.md) for a step-by-step guide, and the two
reference plugins:

- `plugins/battery_monitor/` — read-only **sensor** pattern.
- `plugins/cabin_light/` — controllable **actuator** pattern (with safety).
- `plugins/diesel_heater/` — **climate** actuator with a setpoint; exercises both
  the battery load-shedding and fuel-required safety rules.
- `plugins/water_system/` — **water** tanks (fresh/grey) + a pump with dry-run
  protection; the pump is `essential` so it is never load-shed.
- `plugins/vehicle/` — **vehicle** GPS/speed/heading/odometer/ignition sensors
  (read-only, like a real OBD/GPS feed). The sim engine dead-reckons position
  from speed+heading; the `LongDrive` advisor suggests breaks.

---

## Repository layout

```
openvan/
  core/                 Python Core (offline-first brain)
    openvan_core/       the package
    tests/              pytest — the AI feedback loop
    pyproject.toml
  plugins/              one package per plugin
    battery_monitor/  cabin_light/  diesel_heater/  water_system/
  ui/                   React + Vite — the product UI (OpenVan OS, :5173)
  bench/                React + Vite — the Hardware Bench (dev sim, :5174)
  shared/               api client, types, WebSocket hook (used by ui + bench)
  package.json          npm workspace root (ui + bench)
  docs/
    PLUGINS.md          how to write a plugin (+ bench/product support)
  backlog.md            future ideas, deliberately not built yet
  CLAUDE.md             (this file)
  README.md
```

**Settings live at runtime.** `Core.settings()` / `Core.apply_settings()` back the
Admin UI (`/api/settings`, `/api/models?connectivity=…`) — offline/online model
config, the global `connectivity` mode, AI enable, sim toggle. The same surface the
**MCP server** exposes (`mcp_server.py` → `OpenVanClient` in `apiclient.py`, a
thin httpx bridge to the running REST API — one Core, no duplicated loops; `mcp`
is an optional extra). Changes publish `settings.changed` / `assistant.changed`
and **persist to `data/settings.json`** (loaded via `Config.resolve()`:
defaults < persisted < env). The **API key is never persisted** — memory/env only.

**Personalities = voice only** (`personalities.py`): six built-ins + user forks,
persisted to `data/` (gitignored). A personality shapes phrasing, never facts,
intents or safety. The Admin picker shows each one's trading-card artwork
(`ui/public/personalities/<id>.jpg`); forks inherit their base's art. A personality
carries **no** model/connectivity binding — which model answers (local or cloud) is
a single global setting (`Config.connectivity`, Rule 4), independent of the chosen
voice. Online API keys live in memory / env, never on disk.

**Language.** The **product UI** is localised (English / Svenska / Deutsch) via a
tiny in-house i18n (`ui/src/i18n.tsx`: a key→`{en,sv,de}` dict, `useT()`, choice
persisted client-side); the **bench stays English**. The **model** reply language
is a separate global setting (`Config.language`, in `/api/settings`) injected into
every LLM system prompt via `llm.with_language()` — it defaults to the app language
but is overridable, and the directive still lets the model honour a one-off request
("say it in German"). Advisory/notice text is still English (backend) for now.

**Ideas go in [backlog.md](backlog.md)**, not lost in chat — capture, don't build,
until scheduled.

---

## Working on OpenVan

```bash
# Core
cd core && python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                      # must pass before every commit
python -m openvan_core      # serves http://127.0.0.1:8000

# Front-ends (one workspace, two apps — run at the repo root)
npm install                 # installs both ui + bench
npm run dev:ui              # product UI    -> http://localhost:5173
npm run dev:bench          # hardware bench -> http://localhost:5174 (separate terminal)
```

### Standards

- **Tests before features.** New code needs tests; `pytest` must be green.
- **Simple over clever.** If you're proud of how clever it is, simplify it.
- **Physics before code.** Model what the physical system actually does
  (e.g. shed non-essential loads at critical SoC — don't fake a demo).
- **One integration at a time.** Land plugins focused and complete.
- **Simulators are not reality.** Keep improving the twin's realism, and validate
  against real hardware before shipping a backend.
- **Measure, don't guess.** Benchmark timing/energy numbers rather than inventing
  them.

### Branch & PR

- Branch: `{issue-number}-short-description`.
- Keep PRs to one logical change; link the issue; squash-merge.
- A PR that adds a feature without simulator support or tests is incomplete.
