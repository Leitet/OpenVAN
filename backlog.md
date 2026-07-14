# OpenVan Backlog

Ideas worth doing later — captured so they aren't lost, but deliberately **not**
being built right now. Keep entries short. When one gets picked up, move it into
an issue/branch and delete it here.

> Convention: newest ideas at the top of each section. Every feature still
> follows the rules in [CLAUDE.md](CLAUDE.md) (simulator support + tests).

---

## Assistant / AI

### Personalities (selectable companion character) ⭐
The companion should have a **personality** that shapes the tone and voice of its
briefings and replies — the *how it says it*, never the *what* (facts, safety and
intents stay identical).

- Ship **5 built-in personalities** the user can choose from, e.g.:
  1. **Calm Navigator** — measured, reassuring, understated.
  2. **Cheerful Buddy** — warm, upbeat, encouraging.
  3. **Dry Wit** — concise, a little sardonic.
  4. **Zen Minimalist** — few words, serene.
  5. **Expedition Guide** — rugged, practical, adventurous.
- Implementation sketch: a personality = a system-prompt persona (+ maybe
  verbosity/emoji settings) layered onto the companion briefing and the intent
  phrasing. Model-agnostic.
- Selectable in the **Admin UI**; default is a neutral personality.
- Offline-first: the deterministic template still works; personality only
  affects LLM-phrased output. Consider light personality flavour in templates too.
- Stretch: user-defined custom personalities.

### Other AI ideas
- Bigger local model option surfaced in Admin (e.g. `llama3.1:8b`) for sharper
  reasoning on indirect requests.
- Local voice in/out (wake word → STT → intent → TTS briefing), fully offline.
- Assistant should be able to *ask a follow-up* when an intent is ambiguous.

---

## Companion / proactivity
- Time- and context-triggered briefings pushed automatically (a real "good
  morning" at wake time; "you've been driving 2 hours — scenic break?").
- Journey advisors once we have a `vehicle` plugin (driving time, fuel range).
- Snooze / acknowledge notices; per-notice preferences.

## Integrations (plugins)
- Weather (offline core, cloud-enhance) to power "rain in an hour".
- GPS / navigation; `vehicle` plugin (OBD-II, CAN) for speed, odometer, doors.
- Victron, MQTT, Matter, ESPHome, Shelly, Starlink, Home Assistant bridge.

## Telemetry & data
- **Local time-series storage** of all signals/telemetry (battery, solar, temps,
  water, loads, GPS…). Everything saved locally (offline-first) in a time-series
  database, to enable graphs, trends, predictions (e.g. battery runtime, water
  usage rate, solar forecasts) and to feed the AI richer historical context.
  Consider a lightweight embedded TSDB; retention/downsampling policy; export.

## Travel memory
- A living journal: places stayed, dates, weather, photos, notes, energy used.
- "Do you remember that lake two years ago?" recall.

## Admin / platform
- MCP server exposing settings + control (parity with the Admin UI / REST API).
- Auth for the Admin UI; separate it from the simulator for real deployments.
- Per-plugin enable/disable and configuration from the Admin UI.
- Settings persistence (currently runtime-only; survive restarts).

## Simulator realism
- Battery SoC driven by the energy balance (solar − loads) instead of injected.
- Richer thermal model (insulation, sun load); tune constants against a real van.
