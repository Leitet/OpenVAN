# OpenVan Backlog

Ideas worth doing later — captured so they aren't lost, but deliberately **not**
being built right now. Keep entries short. When one gets picked up, move it into
an issue/branch and delete it here. What has shipped lives in
[CHANGELOG.md](CHANGELOG.md).

> Convention: newest ideas at the top of each section. Every feature still
> follows the rules in [CLAUDE.md](CLAUDE.md) (simulator support + tests).

---

## Hardware validation — awaiting real devices (owner: Johan)

Everything below is written to documented protocols but is **unvalidated against real
hardware** (no devices in the dev env). Test on real kit when available, then feed
findings back:

- **Victron** — confirm the CCGX Modbus-TCP register addresses / scale factors and the
  Venus MQTT `N/<portal>/…` topic map on a real Cerbo GX (`integrations/victron_venus`).
- **ESPHome** — validate the `native_api` transport against a real node (entity listing,
  state streaming, auth/encryption); confirm the `aioesphomeapi` version pin.
- **Modbus / MQTT clients** — exercise `transports/` against real brokers/PLCs (framing,
  reconnect, keepalive under real traffic).
- **Real router transports** — Teltonika RutOS Web API, Starlink gRPC, GL.iNet.
- **Voice on the edge box** — whisper+piper are validated end-to-end on the dev
  machine (piper speaks → whisper transcribes back verbatim); on the real Zap/edge
  hardware, profile CPU/latency and pick model sizes (`voice_whisper_model`), and
  pick a per-personality piper voice.
- **Serial links & RTU** — validate the TCP-bridge link against a real EW11-class
  device, the `serial` extra against a USB-RS485 stick, and the EPEver register
  map against a real Tracer.
- **Chinese diesel heater** — validate the blue-wire frames against a real unit
  (with the OEM controller on hand): start/stop commands, 25000 baud over an
  EW11-class bridge, echo behaviour on the single wire, run-state/error maps.
  **Combustion appliance — bench-test outside the van first.**
- **BLE** — validate the bleak radio on a real adapter (Linux/BlueZ + macOS), and
  the BTHome / Ruuvi RAWv2 / Mopeka / TPMS TypeA parsers against real devices, the
  **JBD BMS** frames against a real pack, and **Victron Instant Readout**
  decrypt+records against a real SmartShunt/SmartSolar (formats per public docs /
  community RE / the victron-ble reference, pinned only by synthetic vectors).
- **Simulator realism** — once real telemetry exists, tune the illustrative constants
  (thermal, water, energy, solar cloud-loss) against measured values.
- After each: replace the integration's honest "unvalidated" `warning` with a real
  status, and add a packet capture / fixture to the tests.

---

## Van-life pain points

- **Connectivity follow-ups** (#11): a "guide me back" route/line to the
  better-coverage spot (not just a pin); data-usage / per-SIM stats and a
  "you're roaming" cost hint. (Trail age cap shipped.)
- **Services layer on the map/route** (#12) — water refill, dump/black, LPG,
  fuel points from OSM/Park4Night along the route, and "grey tank full → dump 4 km
  ahead". Framework exists (camp sources + roads); needs a services data source
  (Overpass `amenity=sanitary_dump_station|drinking_water`, blocked in this env).
- **Trip costs** (#13): fuel used × price and per-stay camp fees (needs a
  diesel-consumption estimate + a place to enter fees/price); a per-day breakdown /
  trip history.
- **Security / intrusion push** (#14): shock sensor, an optional siren, and a
  remote "someone's at the van" push once a notification channel exists.
- **Real camera backends** — RTSP/ONVIF snapshots & live streams; per-vendor cloud
  (Reolink/Ring/Blink/Eufy) adapters; local recording + a playback timeline; a
  **Frigate NVR bridge** (local AI object detection, HA-native); PTZ + two-way
  audio; motion→auto-record when armed; snapshot thumbnails in the intrusion notice;
  an interior-cam privacy shutter when disarmed. See `docs/CAMERAS.md`.
- **Park nose-south for morning charge** (#15) — an orientation hint (needs panel
  azimuth + the sun's azimuth, not just elevation).
- **Cassette dump finder** — the CassetteFull advisor shipped (#17); the "find an
  emptying point" map layer waits on the services layer (#12).
- **Pet mode push alert** — the aboard-toggle + tightened band shipped; a remote
  push needs a notification channel (see #14).
- **Routines follow-ups** (the full automation builder SHIPPED: editable
  routines with manual/sensor/time triggers, ordered actions, waits,
  only-continue-if guards, notify steps — Settings → Routines): surface
  `routine.notify` in the companion/notices; more trigger types (sunrise/
  sunset offset, van events like park/drive-off); duplicate-routine button;
  bind Goodnight's sleep temperature to the learned preference.
- **Maintenance polish** — user-editable intervals; per-item history; odometer
  baseline from a real "install" reading rather than the interval window.

## Assistant / AI

- **Wake word** — "Hey Van" via a small local model (follows the voice pipeline).
- Bigger local model option surfaced in Admin (e.g. `llama3.1:8b`) for sharper
  reasoning on indirect requests.
- Assistant should be able to *ask a follow-up* when an intent is ambiguous.

## Companion / proactivity

- Time- and context-triggered briefings pushed automatically (a real "good
  morning" at wake time; "you've been driving 2 hours — scenic break?").
- Journey advisors (driving time, fuel range) on the vehicle data.
- Snooze / acknowledge notices; per-notice preferences.

## Integrations

- **World-sim provider cards — SHIPPED for all domains** (energy, water/tanks,
  climate/air, vehicle/GPS, fridge, connectivity, security, cameras). Every
  visible value now traces to an installed integration; `seed_twin` holds only
  actuator rest-states, the HA presence input and the sim clock. Plug-and-play
  is contract-tested per card (remove → unknown, re-add → seeded, bare van
  stays alive).
- **HA bridge follow-ups** (export shipped): *import* other HA devices into the
  van (HA entities → twin signals, surfaced like device_sensors); Matter later;
  validate against a real Home Assistant instance (only mosquitto validated so far).
- **Device-control follow-ups** (safety-layer writes shipped for switches):
  ESPHome *lights* (brightness/colour, needs a light entity model beyond on/off) and
  other control types (numbers, covers); Victron control writes (inverter on/off,
  charge limits) over Modbus/MQTT — register maps are device-critical, validate on
  real hardware first; validate ESPHome switch control against a real node.
- **VE.Direct (USB serial)** for Victron products without a GX.
- **RuuviTag BLE scan** and **Autoterm UART** real transports.
- **Signal freshness / staleness** — when a live transport drops, a reader driver
  leaves its last value frozen with no marker; add per-signal freshness or a
  `live=false` banner so stale readings aren't shown as current.
- **Discovery** — mDNS/DHCP/BLE auto-fills host/port so the user rarely types an IP.
- **Vehicle-aware routing** — maxwidth checks + the Journey "restrictions ahead"
  strip shipped; remaining: a height/weight/width-aware route planner
  (OSRM/Valhalla profile from the vehicle dimensions).
- Navigation / routing + destination ETA; OBD-II / CAN detail for the vehicle plugin.
### Integration roadmap — market-scouted 2026-07

Replaces the old "Fas 2–4" list. Built from three parallel research passes over
commercial products, user communities (incl. Husbilsklubben/Wohnmobilforum) and
the HA/ESPHome smart-van scene — full evidence + sources in
[docs/INTEGRATION-MARKET-RESEARCH.md](docs/INTEGRATION-MARKET-RESEARCH.md).
Every pick below has both *demand evidence* and (unless marked) an *existing
open/RE'd protocol base* to build on.

**Substrate — shipped 2026-07** (`ble.py`): one shared scanner/radio, filtered
subscriptions, sim radio + bench injection, bleak as the optional `ble` extra.
First drivers landed on it: **BTHome**, **Mopeka** (mirrors into core tank
signals → existing advisors work on real hardware), **RuuviTag real mode**.
Remaining substrate work (GATT sessions + TPMS TypeA shipped 2026-07):
- Remaining passive parsers: other TPMS families (SYTPMS/Michelin/WODHMIEY) and
  **BM2/Junctek shunts** — small additions on the existing pattern.
- Per-device aliasing/bind UI (name a MAC "fridge probe", assign a Mopeka puck to
  a tank from the library card).

**Wave 1 — status after the 2026-07 autonomous build session:**
1. **Truma iNet-box emulation** (LIN) — REMAINS (the biggest one). The transport
   is no longer a blocker (the link layer reaches the LIN adapter via a TCP
   bridge or the `serial` extra); what remains is the protocol port from
   inetbox.py/esphome-truma_inetbox (license check first).
2. **BLE BMS — JBD/Overkill SHIPPED** (`ble_bms`, GATT, feeds house_battery so
   all advisors/safety run on non-Victron packs). Remains: JK, Daly, Seplos
   protocol modules in the same driver.
3. **Chinese diesel heaters — SHIPPED** (`chinese_heater`: the Ray-Jones/
   Afterburner blue-wire frames — 0xA0/0x05 commands, Modbus CRC MSB-first,
   half-duplex echo handling, non-standard 25000 baud — over the link layer;
   follows the safety-approved `diesel_heater.*` twin state, telemetry back as
   `cdh.*` auto-entities). Remains: BLE-controller variants
   (warehog/esphome-diesel-heater-ble) and fixed-Hz mode surfaced as a setting.
4. **Victron BLE Instant Readout — SHIPPED** (`victron_ble`: pure-stdlib AES-CTR
   FIPS-pinned, battery-monitor + solar records, per-device keys, optional
   house-battery mirror). Remains: more record types (DC-DC, inverter, aux modes).
5. **Garnet SeeLevel II** — REMAINS (12V pulse bus needs GPIO/ESP hardware — an
   ESPHome-bridge recipe is the realistic path; document rather than driver?).
6. **Votronic** (UART/BLE, RE'd) — REMAINS; transport unblocked (link layer for
   the display UART, GATT substrate for the BLE Connector) — remaining work is
   the protocol port from syssi/esphome-votronic.

**Wave 2 — strong demand, mostly easy:**
**BLE TPMS TypeA SHIPPED** (`tpms`; SYTPMS/Michelin/WODHMIEY families remain) ·
MaxxFan IR (protocol decoded; needs an IR bridge recipe) · Dometic **CFX3** +
Alpicool/Brass Monkey BLE fridges (GATT — substrate ready) · EcoFlow (**local
BLE**, not cloud — Rule 3) / Bluetti BLE / Anker SOLIX (official local Modbus-TCP
→ near-free on our driver) · **EPEver SHIPPED** (`epever`: Modbus RTU over the
link layer — EW11 TCP bridge with zero extras, or USB via the `serial` extra;
live PV feeds solar.power) · Starlink local gRPC (grpc dep decision; GPS dropped from local API
2026-05) · OBD-II via **WiCAN** (rides our MQTT client — good next candidate) ·
Shelly 12V (HTTP RPC, loopback-testable) + Tasmota (rides our MQTT client;
VanPi-ecosystem compat) · Simarine Pico (passive UDP — easy) · Webasto/
Eberspächer W-Bus (serial) · Micro-Air EasyTouch (GATT).

**Wave 3 — strategic/regional bets:**
RV-C via CoachProxyOS's decoded tables (the US motorhome gateway) · Lippert
OneControl (dominant NA towables — only a fragile cloud-bridge path; watch) ·
Gobius (Swedish tank radar — partner opportunity) · Frigate/RTSP (integrate,
don't build) · Signal K bridge (also our route to NMEA 2000 — don't build native
N2K) · Schaudt EBL + **Alde** (heavy Nordic/DE demand, closed buses, RE thin —
watch; Alde partially reachable via the Truma iNet path) · VanPi/Pekaway interop
(documented MQTT/HTTP API; courts the nearest existing community).

**Demoted with evidence:** CZone (no DIY demand; someday a Signal K/N2K profile)
· CI-BUS standalone (too early; Truma emulation is the practical value) · CBE,
Thetford (no visible demand) · E&P/AL-KO, REDARC, BMPRO, Sargent, Lithionics
(closed, no RE base — watchlist).

**Pain points the roadmap serves** (aim advisors here too): remote heater
control · tank levels that work · app fragmentation (the unified dashboard *is*
the product) · monitoring-while-away (battery/fridge/**pet safety**) ·
security/theft.
- **Safety-class-4 gating** — locks / gas valves need strong auth + audit +
  isolation before any such integration ships (never free LLM access).
- **Library at scale (thousands of integrations)** — the local foundations shipped
  (manifest registry decoupled from code, signed + versioned packages, trust tiers,
  `/api/drivers`). Remaining: a hosted store index with server-side search +
  pagination + facet counts; on-demand download/install + an update channel
  (community vs. certified); per-integration logos and richer detail pages; fuzzy
  search + synonyms and popularity sort.
- **Driver ecosystem follow-ups** — key rotation/revocation for store keys; a
  `driver.toml` schema for plugins/campsources parity (they load contained today
  but only integrations surface trust); process/sandbox isolation research for
  untrusted drivers (in-proc Python can't be sandboxed — document threat model).

## Telemetry & data

- Battery-runtime **advisor** using the real drain rate (the advisor still uses
  instantaneous current; predictions already expose the trend-based ETA).
- Configurable per-signal retention; anomaly detection on trends.

## Travel memory

- **Photos** attached to a stay (needs file upload/storage).
- **Reverse geocoding** for automatic place names (keyless Nominatim, with a
  cached/offline fallback).
- Conversational recall ("remember that lake two years ago?") — wire travel memory
  into the chat Q&A surface.
- Map markers for past stays on the Journey map.

## Admin / platform

- Auth for the Admin UI and the REST/MCP surface.
- Per-plugin enable/disable and configuration from the Admin UI.
- MCP over HTTP/SSE (currently stdio) for remote clients.

## Simulator realism

- Battery SoC driven by the energy balance (solar − loads) instead of injected.
- Richer thermal model (insulation, sun load); tune constants against a real van.
