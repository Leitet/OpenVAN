# Integration market research — 2026-07

Three parallel research passes over (1) commercial van/RV control products, (2)
user communities — Reddit, iRV2, Ford Transit USA, Sprinter-Source, DIY Solar
Forum, **Husbilsklubben.se**, Wohnmobilforum/German smart-Wohnmobil blogs — and
(3) the Home-Assistant/ESPHome smart-van scene (HACS/GitHub traction = proven
demand *and* proven protocol). This file preserves the evidence; the actionable
roadmap lives in [backlog.md](../backlog.md).

## The one cross-cutting engineering insight

**Almost everything the market wants is BLE.** BMS, tank sensors, TPMS, fridges,
thermometers, heater controllers, power stations, shunts — a first-class shared
**BLE substrate** (scan, advertisement parsing, GATT sessions, one radio shared
across drivers) makes 8+ of the integrations below cheap. Highest-leverage
engineering investment identified by this research. A single **passive-
advertisement family driver** (the RuuviTag pattern generalised) covers Mopeka +
TPMS + BM2 shunts + BTHome/Govee/Xiaomi thermometers in one listener.

## Top user pain points (aim advisors/product here)

1. **Heater control from bed / remotely, blocked by closed protocols** — Truma/
   Alde have no open API (EU); Chinese-heater apps are poor (global). The largest
   volume of DIY reverse-engineering in the space exists to fix exactly this.
2. **Tank levels that actually work** — stock senders are famously wrong; people
   bolt on Mopeka/SeeLevel/Gobius and want one dashboard + real alerts.
3. **App fragmentation** — one app per device (quote from Husbilsklubben) is *the*
   reason vans run Home Assistant; the unified dashboard is the product.
4. **Monitoring while away** — battery in storage, fridge temp (food), cabin temp
   (**pet heat-safety** — the emotional #1 in US threads), behind CGNAT LTE.
5. **Security/theft** — movement alerts, hidden GPS, cameras that talk to nothing.

## Unanimous top picks (all three passes converged)

| Integration | Why | Protocol base |
|---|---|---|
| **Truma iNet-box emulation** | #1 demand signal found anywhere: 1000+-post HA thread, an entire cottage industry of guides; *the* EU heater/boiler; also our LIN/CI-BUS beachhead | inetbox.py, inetbox2mqtt, esphome-truma_inetbox — three mature RE stacks |
| **Multi-brand BLE BMS** (JK, JBD, Daly, Seplos, ANT, SOK…) | The heart of every budget/DIY LiFePO4 build; unlocks SoC-based safety rules on non-Victron vans | BMS_BLE-HA (HACS *default* repo), batmon-ha, syssi/esphome-jk-bms — one multi-vendor driver, not per-brand |
| **Chinese diesel heaters** (Hcalory/Vevor "blue-wire" UART; BLE + Afterburner variants) | Highest unit volume in the space; junk stock apps; natural sibling of our Autoterm driver | Ray Jones RE, cdh-esphome, esphome-chinbasto, hcalory-ble |

## Strong convergence (two passes or one with heavy evidence)

- **Victron BLE Instant Readout** — official documented BLE adv (+AES key); most
  vans have a SmartShunt/SmartSolar but **no GX device** — our Venus driver misses
  them. Easy, official. (esphome-victron_ble, victron-ble)
- **Votronic** — "the German Victron", OEM in Hymer/Knaus-class vans; RE'd UART +
  BLE (syssi/esphome-votronic); explicit HA feature requests; nobody covers it.
- **Mopeka** (LPG/tank BLE) — HA-core + ESPHome-core level documentation; trivial.
- **Garnet SeeLevel II** — de-facto NA tank sender (200k+ installs); 12V pulse
  protocol RE'd since 2015 (esphome-seelevel); tank data feeds our advisors.
- **MaxxFan/MaxxAir IR** — the roof fan; no API at all, IR protocol fully decoded
  (esphome-maxxfan-protocol); people hide ESP32 IR blasters inside the fan.
- **BLE TPMS** — 1000+-post ESPHome thread; several RE'd adv formats (tpms_ble,
  DJTPMS); passive scan.
- **BLE thermometers / BTHome** (Govee, Xiaomi-ATC, SwitchBot) — fridge + pet
  safety; BTHome is the converging open standard — support it first.
- **Fridges**: **Dometic CFX3** (BLE/WiFi DDMP RE'd — keshavdv/dometic-cfx3; an
  explicit "no integration exists" gap) and **Alpicool/Brass Monkey** (cheap BLE,
  GATT RE'd; enormous volume).
- **Power stations**: **EcoFlow** (prefer community BLE-local — ha-ef-ble — over
  the cloud MQTT per Rule 3), **Bluetti** (bluetti_mqtt BLE RE), **Anker SOLIX**
  (official **local Modbus-TCP** HA integration — may ride our Modbus driver
  nearly free).
- **EPEver** — ship as a register-map *preset* on the existing Modbus driver, not
  a new transport.
- **Starlink** — local gRPC, HA-core precedent (~2.7k installs). Caveat: GPS
  removed from the local API for standard plans (May 2026).
- **OBD-II via WiCAN** — meatpiHQ/wican-fw speaks MQTT with autodiscovery already;
  target WiCAN first, generic ELM327 later.
- **Shelly (12V)** + **Tasmota** — explicitly chosen by builders for 12V relay
  duty; Tasmota also = VanPi/Pekaway ecosystem compatibility.
- **Simarine Pico** — premium build monitor; passive WiFi-UDP broadcast RE'd
  (Pico2SignalK) → easy read-only driver.
- **BM2/BM6 + Junctek BLE shunts** — ubiquitous <$30 monitors; trivial passive BLE.
- **Webasto/Eberspächer W-Bus** — big OEM base, cloud+subscription apps resented;
  W-Bus serial RE'd (H4jen/webasto, esphome-webasto).

## Strategic / regional

- **RV-C** (NA motorhomes: Tiffin/Entegra/Newmar) — CoachProxyOS was open-sourced
  (decoded DGN tables to reuse), rvc2hass + RV-Bridge active, LibreCoach community
  proves post-commercial demand. The gateway to the US motorhome market.
- **Lippert OneControl** (NA towables) — dominant but proprietary "IDS-CAN";
  only a fragile cloud-bridge path exists today. Watch.
- **Gobius Pro/C** (Swedish!) — tank micro-radar, BLE + NMEA 2000; Nordic partner
  opportunity; N2K side arrives via Signal K.
- **Micro-Air EasyTouch** — the NA RV thermostat retrofit; BLE, HACS project exists.
- **Frigate/RTSP** — integrate (don't build) for cameras; dedicated camper-Frigate
  HA thread exists; ties into our existing camera backlog.
- **Signal K bridge** — proven MQTT-bridge pattern; also our route to NMEA 2000
  (don't build native N2K).
- **Schaudt EBL** — in nearly every German-built motorhome; proprietary LIN, no
  working OSS yet — hard but differentiating. **Alde** (Swedish, hydronic): heavy
  demand in the same threads but RE stalled; partial path via the Truma iNet box.
  Keep both on watch.
- **VanPi/Pekaway interop** — the closest existing "van OS"; documented HTTP+MQTT
  API; consuming it validates our roadmap and courts its community.

## Demoted, with evidence

- **CZone** — no OSS traction/DIY demand; monitoring PGNs are just NMEA 2000 →
  a profile on Signal K/N2K someday, not a driver.
- **CI-BUS standalone** — only appearing in brand-new OEM gear; Truma emulation
  delivers the practical value today.
- **CBE, Thetford** — no visible integration demand found in any community.
- **E&P/AL-KO leveling, REDARC RedVision, BMPRO, Sargent EC, Lithionics** —
  closed protocols, no RE base; watchlist only (Sargent = UK-market gap if ever
  cracked).
- **Native NMEA 2000** — thin in vans; reach it through Signal K.

*Research run 2026-07 by three parallel scouts with web access; source links
retained in the agent reports (HA community threads, GitHub repos, forum posts,
vendor docs) — key ones inline above.*
