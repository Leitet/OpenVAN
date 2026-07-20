# OpenVan integration landscape

The strategic map for hardware support. **OpenVan supports protocols and
ecosystems, not one bespoke integration per model.** A device speaks a protocol; a
driver normalises it into OpenVan's schema; the safety/capability layer gates it;
the dashboard, AI and Home Assistant consume the normalised entity.

```
device protocol → OpenVan integration (driver) → normalised entity
                → safety & capability layer → dashboard / AI / automation / HA
```

> Popularity ranks are a **weighted judgement** (forum frequency, ecosystem size,
> how established a product is in the camper/marine segment, likelihood an OpenVan
> user owns it) — there's no comprehensive public sales data for van builds.

## Three layers (how this fits the existing code)

- **Backends** (`backends.py`, the `Backend` seam) — the raw transport: `read` /
  `write` / `watch` a signal. `SimBackend` today; `VictronBackend`, `ModbusBackend`,
  `MqttBackend`, … later.
- **Integrations** (`integrations.py`, this doc) — a **driver + descriptor**: connects
  to an ecosystem over one or more transports and **normalises** device data into the
  twin's schema, with machine-readable metadata (transport, local, offline, safety
  class, confidence/status, permissions). Discovered from `integrations/`.
- **Plugins** (`plugins.py`) — the **feature/entity** layer: semantic entities
  (`sensor.house_battery_soc`, `light.cabin`) built on whatever backend/integration
  provides the signals. Unchanged.

Every integration ships a **simulation provider** so it's exercisable against the
twin with no hardware (Rule 1). Real transports slot into the same driver via
`run_transport()` (see `transports/`): pure-stdlib async clients, no vendor SDKs,
each verified against an in-process loopback server. A driver only owns the signals
while `live`; unreachable hardware falls straight back to `simulate()`
(offline-first). **Victron already runs for real** over `modbus_tcp` (GX register
block) and `mqtt` (Venus `N/<portal>/…`) — pending validation on a physical GX.

## Taxonomy (machine-readable)

**Transport**: `mqtt`, `modbus_tcp`, `modbus_rtu`, `ve_direct`, `ble`, `serial`,
`http`, `websocket`, `canbus`, `rv_c`, `nmea2000`, `signalk`, `cloud_rest`,
`native_api`, `zigbee`.

**Confidence / status** (what the user sees, robust → fragile):
`native` (documented local protocol) · `certified` (vendor-approved) · `open`
(public documented API) · `community` (stable community driver) · `experimental` ·
`reverse_engineered` · `cloud_dependent` (no offline) · `read_only` · `unsupported`.

**Safety class** (0 safest → 4 most dangerous): 0 read-only sensor · 1 low-risk
control (lights) · 2 moderate (pump/fan) · 3 high (heater/inverter/energy) · 4
critical / cloud / reverse-engineered.

**Permissions**: `read` (R) · `control` (W) · `configure` (C), each `true` /
`false` / `limited`.

Descriptor example:

```yaml
integration:
  id: victron_venus
  transports: [mqtt, modbus_tcp, ve_direct, cloud_rest]
  local: true
  offline_capable: true
  discovery: mdns
  permissions: { read: true, control: true, configure: limited }
  safety_class: 3
  status: native
```

A fragile one is honest about it:

```yaml
integration:
  id: webasto_thermoconnect
  transports: [cloud_rest]
  local: false
  offline_capable: false
  safety_class: 4
  status: reverse_engineered
  warning: "May break without notice."
```

## Priority classes

`P0` must be in the first useful version · `P1` early · `P2` breadth · `P3`
niche/experimental.

## Category map (condensed)

| # | Category | Lead ecosystems | Best transport | Priority |
|---|----------|-----------------|----------------|----------|
| 1 | **Energy hubs** | Victron GX/Venus OS, Renogy ONE, EcoFlow, Dometic N-BUS | MQTT / Modbus TCP / VE.Direct | P0 |
| 2 | **Battery monitors / BMS** | Victron SmartShunt, JK/JBD BMS, Renogy shunt, Daly | VE.Direct, BLE, UART/RS-485, CAN | P0 |
| 3 | **Solar controllers** | Victron SmartSolar, Renogy Rover, EPEver Tracer | VE.Direct, Modbus RTU, BLE | P0 |
| 4 | **DC–DC / alternator** | Victron Orion, Renogy DCC, Sterling, Redarc | BLE, GX, RS-485 | P0 |
| 5 | **Inverters / chargers** | Victron MultiPlus, Renogy, EcoFlow, Mastervolt | VE.Bus via GX, MQTT, Modbus | P0 |
| 6 | **Heaters (diesel/gas/water)** | Autoterm, Truma, Webasto, Eberspächer | UART/W-Bus, TIN/CI-BUS, cloud | P0 (Autoterm) / P1 |
| 7 | **A/C & ventilation** | MaxxFan, Dometic, Truma Aventa | IR/ESPHome, relay/PWM, CI-BUS | P1 |
| 8 | **Fridge / freezer** | Dometic CFX, Vitrifrigo, Alpicool | BLE/app + external temp/door/current | P1 |
| 9 | **Water / pumps / leak** | resistive senders, Victron GX Tank, SeeLevel, Mopeka, Shurflo | analog, USB→GX, BLE, relay+current | P0 |
| 10 | **LPG / fuel level** | Mopeka Pro, Truma LevelControl, load cell | BLE, resistive, HX711 | P1 |
| 11 | **Leveling / inclinometer** | ESP32 + LIS2DW12/MPU-6050, E-Trailer, Murata SCL3300 | I²C/SPI → MQTT | P0 |
| 12 | **Environment / air quality** | ESPHome, RuuviTag, Shelly H&T, Sensirion SCD4x, BME680 | native API, BLE, MQTT, I²C | P0/P1 |
| 13 | **Lighting / relays / IO** | ESPHome, Shelly, Victron GX relays, CZone, VanPi | native API, HTTP/RPC, MQTT, NMEA2000 | P0 |
| 14 | **Doors / security / cameras** | reed/PIR/mmWave, ONVIF/RTSP cams, Teltonika GPS | Zigbee, digital IO, RTSP/ONVIF | P1 |
| 15 | **Connectivity / router** | Teltonika RUTX, Starlink, Peplink, GL.iNet, MikroTik | RutOS API, gRPC, SNMP, MQTT | P0 |
| 16 | **GPS / navigation** | u-blox USB, phone, Teltonika GNSS, Signal K | NMEA 0183, REST/WS | P0/P1 |
| 17 | **Vehicle / OBD-II** | OBDLink, ELM327, CANable, Comma Panda | BLE/Wi-Fi/USB-CAN | P1 (**read-only** on the vehicle CAN) |
| 18 | **Toilet / black water** | Thetford, Dometic CT, SeeLevel | level signal, CI-BUS | P2 |
| 19 | **Appliances / galley** | induction, kettle, microwave | measure via inverter/shunt (rarely control) | P2 |
| 20 | **Home Assistant / smart home** | HA, MQTT discovery, Matter | MQTT, REST/WS, Matter | P0 |

Full per-model tables (protocols, libraries, packet captures, test status) grow in
this file as integrations land.

## Design rules that shape the code

- **Data provenance.** The AI must never say "battery is 82 %" without knowing the
  **source** (BMS SoC vs. shunt SoC vs. OpenVan estimate) and a **confidence**. The
  normalised schema carries `source` + `confidence`.
- **Safety detectors stay independent.** CO / LPG / smoke alarms must work on their
  own; OpenVan may *read* their alarm line but is never the only safety function.
- **Vehicle CAN is read-only** in the base platform. No arbitrary CAN writes / no
  vehicle-function control.
- **Locks / gas valves / anything dangerous** → `safety_class` 4: strong auth,
  physical presence or separate approval, never free LLM access, full audit,
  isolated from other plugins.
- **Cloud is the last resort** and always flagged `cloud_dependent` (won't work
  offline). Offline-first (Rule 3) means the core control path never depends on it.

## Normalised energy schema (the anchor)

```yaml
energy:
  battery: { state_of_charge, voltage, current, power, time_remaining, source, confidence }
  solar:   { power, yield_today }
  alternator: { power }
  shore:   { connected }
  inverter: { on, ac_load, temperature }
```

## Home Assistant federation

OpenVan both **imports from** and **exports to** HA (MQTT discovery, webhooks,
REST/WS, Matter later) — `sensor.openvan_battery_soc`, `climate.openvan_cabin`,
`binary_sensor.openvan_home`, … When the van comes home it **federates selected
entities**; it never disappears into HA.

## Development order (Fas 1–4)

> **2026-07 update:** Fas 2–4 have been re-planned from market research (three
> scouted passes over products, forums and the HA/ESPHome scene). The current
> wave plan lives in [backlog.md](../backlog.md) ("Integration roadmap —
> market-scouted"); evidence in
> [INTEGRATION-MARKET-RESEARCH.md](INTEGRATION-MARKET-RESEARCH.md). Headlines:
> Truma iNet emulation, multi-brand BLE BMS and Chinese diesel heaters are the
> unanimous top picks; a shared **BLE substrate** is the highest-leverage
> engineering investment; CZone/CBE/Thetford demoted for lack of demand.

**Fas 1 — reference van & core:** MQTT · HA discovery · ESPHome · Victron GX (MQTT)
· Victron Modbus TCP · VE.Direct (USB) · generic ESP32 IO · leveling sensor ·
temp/humidity/CO₂ · tank level + water pump · Teltonika router · USB-GPS · Autoterm
heater.

**Fas 2 — the common alternatives:** Renogy · JK/JBD BMS · EPEver · EcoFlow ·
Mopeka · RuuviTag · Shelly · OBD-II · MaxxFan module · Signal K.

**Fas 3 — factory motorhomes:** CI-BUS · RV-C · NMEA 2000 · Truma iNet X/TIN ·
Dometic N-BUS · CZone · Schaudt · Nordelettronica · CBE · Thetford/Dometic OEM.

**Fas 4 — vendor partnerships:** Truma · Webasto · Dometic · Eberspächer · Thetford
· Garmin/CZone · AL-KO · E&P Hydraulics · Revotion · EcoFlow.

## Top 10 at launch

1. **Victron Venus OS / GX** — covers almost the whole energy system
2. **ESPHome** — own sensors and IO
3. **Home Assistant / MQTT** — makes the van part of the home
4. **Victron VE.Direct** — works without a Cerbo GX
5. **JK/JBD BMS** — the big DIY battery market
6. **Renogy** — the common Victron alternative
7. **Autoterm** — local, realistic heater control
8. **Teltonika RutOS** — internet, GPS and system gateway
9. **RuuviTag / BLE sensors** — easy wireless environment monitoring
10. **Generic Modbus RTU/TCP** — unlocks huge amounts of kit

---

*Sources: Victron (Modbus-TCP/MQTT docs), Renogy OpenAPI, EcoFlow developer
platform, Truma iNet X, Webasto ThermoConnect, VanPi/Pekaway (Autoterm UART),
MaxxAir, E-Trailer (CI-BUS), Ruuvi docs, Shelly API, Teltonika Web API, Signal K,
plus Home Assistant / Victron / DIY Solar / camper communities. Status = current
best judgement; each row hardens as a real driver + packet capture lands.*
