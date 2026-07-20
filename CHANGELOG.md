# OpenVan Changelog

What has landed, newest first. The forward-looking list lives in
[backlog.md](backlog.md); architecture in [CLAUDE.md](CLAUDE.md).

## 2026-07 — Library scroll fix + prefix auto-derivation

- **Fixed**: the integration library reset its scroll position (and search
  focus) on every WS tick — the view was a component defined inside its parent,
  so each render remounted it. It is a plain render function now.
- **Self-containment completed**: `device_sensors` now honours every signal
  prefix declared by an enabled driver's `provides`
  (`IntegrationManager.declared_prefixes()`, cached, world-sim providers
  excluded) — an external driver's readings become entities with no edits to
  any bundled list. Core-mirror entries never hijack existing entities.

## 2026-07 — Simulator cards clearly marked

- Every simulated data source (the world-sim providers + the master switch)
  now carries a dashed **Simulator** badge with the flask glyph on its card —
  in the installed view *and* the library, where there is no grouping to rely
  on. Tooltip: "Simulated data source — not real hardware."

## 2026-07 — Plug-and-play bench: signal browser + integration toggles

- The twin now records each signal's **last writer** (`VanTwin.sources()`,
  exposed in `/api/state` and the WS snapshot), so tooling can group signals
  by the integration that provides them.
- The bench's read-only signal inspector became a **Signal browser**: an
  auto-generated, filterable injector for *every* twin signal, grouped by data
  source — booleans toggle, numbers/strings edit inline. A new integration's
  signals appear there the moment it emits them, with zero bench code.
- The bench's Integrations card can now **add** any catalog driver, not just
  remove installed ones — a new driver is fully plug-and-play from the bench
  alone: enable it, watch its signal group appear, inject, see the product UI
  react.
- Rule 1 updated: hand-crafted bench sliders are for curated scenarios only;
  coverage of new signal keys is automatic.

## 2026-07 — Everything is an integration: world-sim provider cards

- The reference van's data (battery/solar, water/tanks, climate/air,
  vehicle/GPS) is no longer baked into the twin's seeds — it is **provided** by
  four removable `WorldSimProvider` integrations (`sim_energy`, `sim_water`,
  `sim_climate`, `sim_vehicle`), installed by default. Remove one and its
  domain honestly reads "—" (signals released to `None`) instead of frozen
  fake values; the physics engine only evolves domains whose provider is
  installed.
- **Per-domain mixed mode**: a provider never overwrites a value another
  source already supplies, so a real BMS can own the battery while the water
  tanks stay simulated — swap each domain to real hardware card by card.
- **Completed for all domains**: `sim_fridge`, `sim_connectivity`,
  `sim_security` and `sim_cameras` cards added — `seed_twin` now holds only
  actuator rest-states, the HA presence input and the sim clock. A
  parametrized **plug-and-play contract test** covers every provider (remove →
  whole domain unknown, physics + advisors keep running, re-add → reseeded)
  plus the bare-van case: all providers removed, the platform stays alive and
  no advisor fires on unknown data.

## 2026-07 — Sim / real / mixed: the simulator card becomes the physics switch

- **Decoupled the two simulations.** The tick loop now always runs; only the
  *world physics* (clock/thermal/water/vehicle/energy) is gated by the sim
  toggle. Per-driver `sim` modes keep ticking regardless — so a real van can
  trial a driver in sim mode next to live hardware ("what happens if I add X"),
  and OpenVan runs fully simulated, fully real, or mixed.
- **The "OpenVan Simulator" card is now an honest switch**: toggling it on the
  Integrations page maps to `Config.simulate` (same switch as Settings →
  System). Paused ≠ uninstalled — the built-in stays, badged "Simulation
  paused", with a Pause/Resume control instead of Remove.
- Catalog rows expose `sim_engine`; the card description no longer claims to
  drive signals it doesn't.

## 2026-07 — Chinese diesel heater driver (Wave 1 #3)

- **`chinese_heater` driver**: the generic "blue wire" heaters (Vevor, Hcalory,
  eBay clones — the highest-unit-volume heater in the van world) over their
  half-duplex single-wire UART. Frames byte-for-byte per Ray Jones' Afterburner
  reverse engineering (fetched, not recalled): 24-byte controller/heater frames,
  0xA0 start / 0x05 stop, Modbus CRC-16 stored MSB-first, non-standard 25000
  baud, echo-skip on the shared wire. Reaches hardware through the link layer
  (EW11-class TCP bridge with zero extras, or the `serial` extra).
- **Rule 2 by construction**: the driver never accepts commands — it follows the
  twin's `diesel_heater.on`/`setpoint`, which only the diesel-heater plugin
  writes *after* the safety layer approved the intent. Tested end-to-end: an
  empty-tank refusal never puts a start frame on the wire.
- Heater telemetry (supply voltage, fan RPM, heat-exchanger temp, glow plug,
  pump Hz, run state, honest error text) flows back as `cdh.*` signals →
  auto-surfaced sensor entities. Sim mode reflects the twin heater (Rule 1).

## 2026-07 — Pluggable serial links + Modbus RTU + EPEver

- **Link layer** (`transports/links.py`): a serial device is reached by a chosen
  *link*, like choosing a driver — `tcp` (EW11/ser2net bridges, pure stdlib,
  works with zero extras), `serial` (USB/UART via the optional `serial` extra),
  `sim` (scripted stand-in). Extensible registry for new link types.
- **Modbus RTU** (`transports/modbus_rtu.py`): CRC-16 framing over any link —
  the protocol RS-485 van gear actually speaks.
- **EPEver driver**: Tracer/XTRA MPPT over RTU; live PV mirrors into
  `solar.power` so forecasting/advisors run on real hardware. End-to-end tested
  against a scripted device; register map flagged for real-Tracer validation.
- The wave-1 "serial blocker" (Truma, Chinese heaters, Votronic, W-Bus) is
  dissolved — those now need only their protocol ports.

## 2026-07 — Autonomous build session (roadmap waves + small items)

- **GATT sessions** in the BLE substrate (programmable SimBleDevice; bleak
  adapter) — connection-oriented BLE drivers now fully testable with no radio.
- **BLE BMS driver** (JBD/Overkill/Xiaoxiang): polls packs over GATT with frame
  reassembly + checksums; feeds `house_battery.*` so every advisor, prediction
  and safety rule runs on a non-Victron pack. (Wave 1)
- **Victron Instant Readout driver**: SmartShunt/SmartSolar broadcasts with no GX
  — pure-stdlib AES-128-CTR (FIPS-pinned, generated S-box), per-device keys from
  VictronConnect, battery-monitor + solar records with sentinel handling. (Wave 1)
- **BLE TPMS driver** (TypeA valve-cap): pressure/temperature/battery/alarm per
  wheel, format fetched from the community reference parser. (Wave 2)
- **Small items**: cassette-toilet tank + advisor (#17) · pet mode (tightened
  cabin band + Comfort toggle) · coverage-trail age cap · CO₂/humidity trend
  sparklines · MQTT SUBACK rejection surfaced · OSM **maxwidth** → NarrowRoad
  advisor (width incl. mirrors) + a Journey "restrictions ahead" strip · scene
  names localised.

## 2026-07 — BLE substrate + first BLE drivers

- **One radio, shared by every BLE driver** (`ble.py`): Core owns a single
  scanner; drivers subscribe with a filter and never touch the radio. Sim radio
  for bench/test injection (`POST /api/sim/ble`), real adapters via the optional
  `ble` extra (bleak), contained subscriber failures, `GET /api/ble` status.
- **BTHome driver** — the open BLE sensor standard (Shelly BLU, Xiaomi-ATC…):
  one driver for every compliant thermometer; auto-surfaced as entities.
- **Mopeka Pro Check driver** — BLE tank pucks, with the level mirrored into the
  core tank signal so the existing propane/water advisors run on real hardware
  unchanged (verified: a low LPG frame fires the untouched LowPropane advisor).
- **RuuviTag real mode** — RAWv2 advertisement parsing on the substrate.
- All parsers are pure functions pinned by test vectors; formats flagged for
  real-device validation.

## 2026-07 — Integration market research

- Three parallel scouted research passes (commercial products, user forums incl.
  Husbilsklubben/Wohnmobilforum, HA/ESPHome smart-van scene) distilled into a
  wave-planned integration roadmap in the backlog + an evidence file
  (`docs/INTEGRATION-MARKET-RESEARCH.md`). Unanimous top picks: Truma iNet-box
  emulation, multi-brand BLE BMS, Chinese diesel heaters. Key insight: almost
  everything is BLE — build the shared BLE substrate first. CZone/CBE/Thetford
  demoted for lack of demand.

## 2026-07 — The driver ecosystem: manifests, signing, containment

- **Manifest-first driver registry** — every driver declares `driver.toml`
  (id/version/kind/`api` level) readable without importing code; API-version
  gating lists future drivers as *incompatible* instead of crashing; external
  drivers without a manifest are refused; user drivers install in `data/drivers/`.
- **Signing & trust chain** — pure-stdlib Ed25519 (RFC 8032, pinned by the RFC's
  own vectors) over a canonical package digest; trust tiers bundled / official
  (store keys) / community (user-trusted keys) / unsigned (allowed, badged);
  `require_signed` lockdown; a signed-then-modified package is **blocked** and
  never loads. `openvan-driver keygen|sign|verify` CLI; provenance badges in the
  library; `GET /api/drivers`. Validated live end-to-end: keygen → sign → trust →
  loads as *community*; tampering the file → CLI says TAMPERED and the van
  refuses it while booting normally.
- **Containment everywhere** — a driver/plugin/camp-source that fails to import
  or set up is logged and shown as an error record; one bad package never bricks
  the van. All bundled integrations now carry manifests.
- `docs/DRIVERS.md` — the community guide: writing, simulating, signing,
  publishing a driver.

## 2026-07 — Safety-checked device controls

- **Integrations can now actuate — only through the safety layer.** The
  `Integration` base gained `register_control()` + `send_command()`: a driver's
  controllable device (an ESPHome relay, …) becomes a switch entity whose commands
  run intent → safety → the driver's transport (or the twin in sim); the device's
  state echo drives the UI. Load-shedding covers every control automatically
  (non-essential by default). ESPHome discovers a real node's switches and pushes
  commands over the native API — with a sim relay so the whole path runs against
  the twin; a refused command never reaches the wire.
- **The inverter switch is genuinely controllable** (was read-only), incl. from
  Home Assistant via the bridge.
- Device controls render as toggles on the Comfort tab; `device_sensors` no longer
  shadows control-owned signals with read-only sensors.

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
