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

- **Connectivity plugin (#11) — core landed.** Internet/signal/network/GPS-fix are
  now core twin state (seeded, bench-driven, read by a router integration on real
  hardware), surfaced by `plugins/connectivity` as entities + a status-bar chip, with
  a `WeakSignal` advisor (offline / weak-signal, offline-first framing). Remaining:
  - **"Better spot back there" locator — landed, incl. map marker.** `coverage.py`
    records a bounded (GPS, signal) trail as the van moves; `WeakSignal` points back to
    the nearest recent strong-coverage spot with distance + compass direction, carries
    the spot in the notice `data` (`better_spot`), and the Journey map shows it as an
    amber signal marker (panning to it when parked with no route). Follow-ups:
    - **"Guide me back"** — a route/line from the van to the better_spot, not just a pin.
    - **Recency/expiry** — the trail is count-bounded, not time-bounded; add an age
      cap so a spot from hours/days ago isn't offered as "just back there".
  - **Real transports**: Teltonika RutOS Web API, Starlink gRPC, GL.iNet — stream
    signal/network/data-usage/GPS in via `run_transport()`.
  - Data-usage / per-SIM stats; a "you're roaming" cost hint.
- **Services layer on the map/route** (#12) — water refill, dump/black, LPG,
  fuel points from OSM/Park4Night along the route, and "grey tank full → dump 4 km
  ahead". Framework exists (camp sources + roads); needs a services data source
  (Overpass `amenity=sanitary_dump_station|drinking_water`, blocked in this env).
- **Trip stats (#13) — v1 landed.** `trip.py` (`TripLedger`) composes distance
  (odometer delta), nights + places (journal), days and solar harvested (telemetry
  integral) from a resettable start marker; Journey-tab "This trip" panel + `/api/trip`
  (GET stats, POST /reset). Remaining: **costs** — fuel used × price and per-stay camp
  fees (needs a diesel-consumption estimate + a place to enter fees/price); a per-day
  breakdown / trip history; and folding the summary into the companion briefing.
- **Security / intrusion push** (#14) — arm/disarm + door/motion/**camera** intrusion
  alarm **shipped** (`security.py`, `plugins/cameras`, Security tab); still to do:
  shock sensor, an optional siren, and a remote "someone's at the van" push once a
  notification channel exists.
- **Real camera backends** — the camera *plugin + entity model + Security-tab UX*
  shipped against the simulator (metadata + stylised placeholder feed). Real video
  is a `Backend` job: RTSP/ONVIF snapshots & live streams; per-vendor cloud
  (Reolink/Ring/Blink/Eufy) adapters; **local recording + a playback timeline**; a
  **Frigate NVR bridge** (local AI object detection, HA-native); PTZ + two-way
  audio; motion→auto-record when armed; snapshot thumbnails in the intrusion notice;
  an interior-cam privacy shutter when disarmed. See `docs/CAMERAS.md`.
- **Solar load-timing advisor (#15) — landed.** `solar_window` picks the next strong
  solar stretch from the hourly forecast; the `SolarWindow` advisor suggests running
  high-draw loads / topping up during it (gated on battery having room), and the Power
  tab's Predictions show "Best solar window: 08:00–16:00 · 456 W". Remaining:
  - **"Run it now" precision — landed.** The simulated forecast is now anchored to the
    twin's clock (`local_solar_datetime`), so the `SolarWindow` advisor knows whether
    *now* is in the window and switches to a "Sun's out — strong sun right now" framing
    (vs. "sunniest stretch is around HH:00–HH:00" when it's still coming).
  - **Park nose-south for morning charge** — an orientation hint (needs panel azimuth
    + the sun's azimuth, not just elevation).
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
GPS / vehicle plugin and weather (open-meteo, offline-first) both landed. A
**vehicle profile** (dimensions/weight/fuel/category + 33 model presets) and
**low-bridge / weight-limit** warnings (height & gross weight vs. OSM
maxheight/maxweight on the road ahead) also landed. Remaining:
- **Vehicle-aware routing** (builds on the vehicle profile + roads.py):
  - **`maxwidth` check** for narrow lanes/tunnels, using width-incl-mirrors.
  - **Surface active height/weight/width limits on the Journey tab** (a small
    "restrictions ahead" strip), not just as a companion notice.
  - **Height/weight/width-aware route planner** — route around low bridges,
    weight-limited roads and narrow lanes (needs a routing engine that honours the
    OSM restriction tags, e.g. an OSRM/Valhalla profile built from the vehicle
    dimensions).
- Navigation / routing + destination ETA (builds on the GPS the vehicle plugin
  now provides).
- OBD-II / CAN detail for the vehicle plugin (doors, fuel, engine data).
- **Integration framework landed** (`integrations.py` + `integrations/`): the
  ecosystem-driver layer with machine-readable descriptors (transport / local /
  offline / permissions / safety_class / status / warning), a status-badged catalog
  (Settings → Integrations + a bench card), enable/disable persistence, and
  sim-backed reference drivers for the launch set (Victron Venus, ESPHome, MQTT/HA,
  Modbus, RuuviTag, Teltonika, Autoterm, Renogy). A **searchable/filterable library**
  (Settings → Integrations → Browse) landed too: a minimal standard set installed by
  default (just the simulator, a non-removable built-in), everything else opt-in.
  Strategy map in `docs/OPENVAN-INTEGRATION-LANDSCAPE.md`.

  **Real transports — the seam + Victron landed.** `transports/` holds pure-stdlib
  async clients (`AsyncModbusTcpClient`, `AsyncMqttClient`, no vendor SDKs), each
  verified against an in-process loopback server. The `Integration` base runs a
  reconnecting transport supervisor with offline-first sim fallback (a driver only
  owns the signals while `live`). **Victron** ships `sim` / `modbus_tcp` (GX register
  block) / `mqtt` (Venus `N/<portal>/…`), configured from the library
  (`/api/integrations/config`). Remaining:
  - **Validate against real hardware** — the Modbus register addresses/scale factors
    and the MQTT topic map are per Victron's published lists but *unverified on a real
    GX*. Confirm on a device before trusting values (simulators are not reality).
  - **VE.Direct (USB serial)** for Victron products without a GX.
  - **ESPHome native API — landed** (`native_api` mode over the optional
    `aioesphomeapi` extra; streams a node's entities into `esphome.<device>.<entity>`
    signals, sim fallback, adapter-isolated + fake-client tested). Remaining: **validate
    against a real node** (unvalidated here — no device/library in this env); surface the
    dynamic `esphome.*` signals as semantic entities on a tab; support **control**
    (switches/lights) back through the safety layer.
  - **MQTT broker + Home Assistant discovery** (import *and* export), Teltonika RutOS
    Web API, RuuviTag BLE scan, Autoterm UART (through the safety layer).
  - **Writes/control** — the transports are read-only so far; actuation (set inverter,
    charge limits, heater setpoint) must route through `Hub.execute_intent` → safety,
    never a bare transport write.
  - **Signal freshness / staleness** — when a real transport drops, a reader driver
    (e.g. Victron, which has no `simulate()`) leaves its last reading frozen with no
    "stale" marker. Add a per-signal freshness/updated-at (or a driver `live=false`
    banner in the UI) so a stale reading isn't shown as current.
  - **MQTT SUBACK** — the client subscribes fire-and-forget; award/log a rejected
    subscription (SUBACK failure 0x80) instead of silently never yielding.
  - **Discovery** auto-fills host/port (mDNS for GX/ESPHome) so the user rarely types an IP.
  - **Normalised entities — energy landed.** The DC energy system (solar yield,
    alternator, shore, inverter) is now environment physics in `simulation.py` and
    surfaced by the `energy_system` plugin on the Power tab (+ a bench Energy card).
    Still to surface as entities: `connectivity.*` (Teltonika), `ruuvitag.*`,
    `esphome.*` on the relevant tabs.
  - **Fas 2–4** (see the landscape doc): JK/JBD BMS, EPEver, EcoFlow, Mopeka, Shelly,
    Signal K, OBD-II; then OEM buses (CI-BUS, RV-C, NMEA 2000, Truma/Dometic); then
    vendor partnerships.
  - **Safety-class-4 gating**: locks / gas valves need strong auth + audit +
    isolation before any such integration ships (never free LLM access).
  - **Library at scale (thousands of integrations)** — today the library filters
    client-side over the full catalog the API returns (fine into the low hundreds).
    For thousands:
    - A **metadata registry / manifest** decoupled from driver code — the catalog is
      descriptors (id, name, category, transport, status, safety, vendor, logo),
      *not* thousands of shipped Python packages. Driver code is fetched/loaded only
      when an integration is added.
    - **Server-side search + pagination + facet counts** behind the same UI
      (`/api/integrations/library?q=&category=&status=&transport=&page=`), so the
      client never holds the whole catalog. Keep `/api/integrations` for the small
      installed set.
    - **Signed, versioned integration packages** + an update channel (community vs.
      certified), and a way to install a driver from the registry on demand.
    - **Per-integration logos/branding** and richer detail pages (setup steps,
      required credentials, supported models) in the library.
    - **Fuzzy search + synonyms** (users search "cerbo", "smartshunt", "batteri")
      and popularity/sort signals.

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
