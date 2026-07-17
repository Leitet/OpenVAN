# OpenVan Backlog

Ideas worth doing later — captured so they aren't lost, but deliberately **not**
being built right now. Keep entries short. When one gets picked up, move it into
an issue/branch and delete it here.

> Convention: newest ideas at the top of each section. Every feature still
> follows the rules in [CLAUDE.md](CLAUDE.md) (simulator support + tests).

---

## Van-life pain points — deferred (2026-07 research session)

From `docs/RESEARCH.md`. The session shipped air/CO safety, condensation,
climate-extreme, scenes, leveling, propane and maintenance. Still open:

- **Connectivity plugin** (#11) — Starlink/LTE/Wi-Fi status + signal strength as
  sensors; a "weak signal, better spot 300 m back" hint. Needs a modem/router
  integration (Teltonika, GL.iNet, Starlink API); build the sensor seam + a sim
  source first.
- **Services layer on the map/route** (#12) — water refill, dump/black, LPG,
  fuel points from OSM/Park4Night along the route, and "grey tank full → dump 4 km
  ahead". Framework exists (camp sources + roads); needs a services data source
  (Overpass `amenity=sanitary_dump_station|drinking_water`, blocked in this env).
- **Cost / trip stats** (#13) — fuel, camp fees, distance, nights; a simple trip
  ledger over telemetry + journal.
- **Security / intrusion** (#14) — motion/door/shock sensors → armed "away" mode,
  alert + optional siren; a "someone's at the van" push. Needs sensors + push.
- **Solar-orientation & load-timing advisor** (#15) — we already compute a
  weather-aware solar forecast; add "best window to run the kettle/charge" and
  "park nose-south for morning charge".
- **Fridge plugin** (#16) — compressor draw, door-ajar alert, food-safety temp log.
- **Black / cassette toilet** (#17) — mirror the grey-tank advisor; cassette-full
  reminder + dump finder.
- **Pet mode** — an explicit "pet aboard" toggle that tightens the cabin-temp
  alarm band and (online) can push an alert; ties into the existing
  `CabinClimateExtreme` advisor.
- **Scene polish** — user-editable scenes and setpoints; bind Goodnight's sleep
  temperature to the learned preference; localise scene names.
- **Maintenance polish** — user-editable intervals; per-item history; odometer
  baseline from a real "install" reading rather than the interval window.
- **Air-quality trends** — log CO2/humidity to telemetry and show the overnight
  curve (helps people see when to crack a vent).

## Assistant / AI

### Voice chat — offline-first STT/TTS ⭐
A first pass ships in the UI: the Assistant tab has **mic dictation** and **spoken
replies** via the browser Web Speech API (`ui/src/voice.ts`), feature-detected and
gated so text always works with no mic. Dictation just fills the text box, so voice
still goes through the safety-checked text-intent path — it never gets its own
control channel.

Next, make it genuinely offline-first and van-grade (browser STT can fall back to a
cloud service and is patchy on iPad Safari):
- **Local STT** — whisper.cpp / faster-whisper / vosk running on the Zap/edge, exposed
  by Core (e.g. `POST /api/voice/transcribe`, or a WS mic stream). The front-end seam
  in `voice.ts` swaps to this.
- **Local TTS** — piper (or similar) for a warm on-device voice; pick the voice per
  personality (voice ≠ model, Rule 4).
- **Wake word** (optional) — "Hey Van" via a small local model.
- **Cloud option** — an OpenAI/Anthropic realtime/audio model as an *enhancement*
  when online, never a dependency (Rule 3).
- Bench support: a way to feed a canned audio clip / transcript so the pipeline is
  testable without a real mic (Rule 1).

### Other AI ideas
- Bigger local model option surfaced in Admin (e.g. `llama3.1:8b`) for sharper
  reasoning on indirect requests.
- Assistant should be able to *ask a follow-up* when an intent is ambiguous.

---

## Companion / proactivity
- Time- and context-triggered briefings pushed automatically (a real "good
  morning" at wake time; "you've been driving 2 hours — scenic break?").
- Journey advisors once we have a `vehicle` plugin (driving time, fuel range).
- Snooze / acknowledge notices; per-notice preferences.

## Integrations (plugins)
GPS / vehicle plugin and weather (open-meteo, offline-first) both landed.
Remaining:
- Navigation / routing + destination ETA (builds on the GPS the vehicle plugin
  now provides).
- OBD-II / CAN detail for the vehicle plugin (doors, fuel, engine data).
- Real device backends: Victron, MQTT, Matter, ESPHome, Shelly, Starlink,
  Home Assistant bridge — implement the `Backend` seam against real hardware.

## Telemetry & data
Local time-series storage complete: SQLite recording, read-time downsampling,
CSV export, write-time hourly/daily rollups (months of history), predictions
(battery/water/diesel ETAs + solar Wh), and predictions fed into the companion
briefing. A weather-aware **solar forecast** (cloud-adjusted expected Wh for the
day) also landed. Possible future work:
- Battery-runtime **advisor** using the real drain rate (the advisor still uses
  instantaneous current; predictions already expose the trend-based ETA).
- Configurable per-signal retention; anomaly detection on trends.

## Travel memory
Living journal landed (`memory.py`: auto-logged stays with GPS/weather/energy,
notes, place names, bookmarks; Journal panel; fed to the companion for recall).
Remaining:
- **Photos** attached to a stay (needs file upload/storage).
- **Reverse geocoding** for automatic place names (keyless Nominatim, with a
  cached/offline fallback).
- Conversational recall ("remember that lake two years ago?") — the chat Q&A
  surface now exists (`/api/chat`); wire travel memory into it.
- Map markers for past stays on the Journey map.

## Admin / platform
Settings persistence and the MCP server both landed (`mcp_server.py` +
`apiclient.py`; 17 tools bridging to the REST API). Remaining:
- Auth for the Admin UI and the REST/MCP surface (the product UI and the bench are
  already separate apps).
- Per-plugin enable/disable and configuration from the Admin UI.
- MCP over HTTP/SSE (currently stdio) for remote clients.

## Simulator realism
- Battery SoC driven by the energy balance (solar − loads) instead of injected.
- Richer thermal model (insulation, sun load); tune constants against a real van.
