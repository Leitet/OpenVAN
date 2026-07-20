# OpenVan Changelog

What has landed, newest first. The forward-looking list lives in
[backlog.md](backlog.md); architecture in [CLAUDE.md](CLAUDE.md).

## 2026-07 — Voice + the Home Assistant bridge

- **Voice** — offline-first STT/TTS behind one seam: sim engines for the bench and
  tests, real faster-whisper + piper as the optional `voice` extra (validated
  end-to-end: piper speaks, whisper transcribes it back verbatim over the API);
  the UI prefers a real Core engine and falls back to the browser speech APIs.
- **Home Assistant bridge** — the van federates into the home: HA MQTT Discovery
  export (one retained "OpenVan" device with every sensor/switch/light/climate),
  live state topics, availability via MQTT Last Will, HA-restart republish, and
  commands from HA routed through the safety layer (refusals snap back). Validated
  live against mosquitto. MQTT client gained Last-Will + retained publishes.

## 2026-07 — UI polish for the van screen

- **Fill-the-screen dashboards** — Home is a 2×2 cockpit that fills the viewport
  (vitals · quick actions · routines · companion); the Assistant chat fills the
  screen with the input pinned. Resize-safe: rows never shrink below content, so
  small windows scroll instead of clipping.
- **Night / driving mode** — a high-contrast dark override on top of any persona
  theme (dark basemap included), toggled from the status bar; *auto* follows the
  van's real day/night from the sim clock / sun physics.
- **Touch targets** — 44px hit areas across small controls; the Trends range picker
  became a proper segmented control (it was unstyled native buttons).
- **Ragged grids fixed** — no more empty cells on Power/Comfort; settings rows keep
  label + control associated on wide screens.

## 2026-07 — Integrations: framework, library, real transports

- **Integration framework** (`integrations.py` + `integrations/`) — ecosystem
  drivers with machine-readable descriptors (transports, local/offline, permissions,
  safety class 0–4, confidence status, honest warnings). Reference drivers for the
  launch set: Victron Venus, ESPHome, MQTT/HA, generic Modbus, RuuviTag, Teltonika,
  Autoterm, Renogy — every one exercisable against the twin (Rule 1).
- **Integration library** — searchable/filterable catalog (category / status /
  transport / offline) behind "Browse"; a minimal standard set installed by default
  (just the built-in simulator), everything else opt-in. Strategy map:
  `docs/OPENVAN-INTEGRATION-LANDSCAPE.md`.
- **Real transports** (`transports/`) — pure-stdlib async Modbus-TCP and MQTT 3.1.1
  clients, loopback-verified; a reconnecting transport supervisor on the
  `Integration` base with offline-first sim fallback. **Victron** speaks
  `modbus_tcp` (GX register block) and `mqtt` (Venus `N/<portal>/…`); **ESPHome**
  speaks the native API via the optional `aioesphomeapi` extra. Both flagged
  unvalidated until real hardware (see backlog).
- **Auto-surfaced device sensors** — `device_sensors` turns arbitrary integration
  readings (`ruuvitag.*`, `esphome.*`, …) into entities with guessed units/names
  (Backend `watch_prefix`/`snapshot`); shown on the Comfort tab.
- **Hardening pass** — MQTT keepalive under steady traffic, per-advisor isolation,
  no false 0% coverage dead-zones, Modbus frame guards, bounded transport teardown.

## 2026-07 — Energy, connectivity, journey intelligence

- **Energy system** — DC energy physics in the simulation (solar yield with midnight
  reset, alternator while driving, inverter warmth under load), surfaced by the
  `energy_system` plugin on the Power tab; bench Energy card.
- **Connectivity** — internet / signal / network / GPS-fix as core twin state with
  a status-bar chip, `connectivity` plugin entities and a `WeakSignal` advisor
  (offline-first framing).
- **Coverage locator** — a bounded (GPS, signal) trail; when signal drops the van
  says "you had 88% about 330 m south of here" and shows the spot on the Journey
  map (amber marker, pans to it when parked).
- **Solar load-timing** — `solar_window` picks the sunniest stretch from the hourly
  forecast; the advisor suggests running high-draw loads then ("Sun's out — right
  now" when the sim clock is inside the window). Power tab shows
  "Best solar window: 08:00–16:00 · 456 W".
- **Unified sim timebase** — the simulated weather forecast is anchored to the
  twin's clock, so sim time, the sun and the solar window agree.
- **Trip ledger** — "this trip" distance / days / nights / places / solar composed
  from the odometer, journal and telemetry, with a resettable start marker;
  Journey-tab panel + `/api/trip`; recapped in the companion briefing.

## 2026-07 — Earlier foundations (research sessions)

- Air & CO safety, condensation, climate-extreme advisors; scenes (goodnight /
  morning / camp / leaving); leveling with vehicle geometry; propane; maintenance
  log; cameras + security tab with intrusion; vehicle profile (33 presets) with
  low-bridge / weight-limit warnings; road-snapped driving on the OSM graph;
  travel journal; conversation memory; weather (open-meteo, offline cache);
  telemetry (SQLite series, rollups, predictions); personalities; MCP server;
  i18n (en/sv/de); the OpenVan Core itself — hub, safety layer, intents, plugins,
  twin, event bus, bench + product UI.
