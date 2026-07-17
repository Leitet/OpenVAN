# Autonomous build session — report

**Brief:** "Deep-research van-life pain points, then address each and build it into
OpenVan. Make assumptions where needed and note them; update the simulator; backlog
what you don't build." Worked unattended, committing after each feature.

## TL;DR

Researched everyday van-dweller pain points (`docs/RESEARCH.md`), then shipped
**seven features across the biggest ones** — safety, damp, ergonomics, leveling,
gas, upkeep, food/fridge and security — each with bench signal injection, a
product-UI surface, and tests, following every rule in CLAUDE.md. Everything
deferred is in `backlog.md`.

- **Tests:** 145 → **177 passing** (+32), whole suite green.
- **Commits:** 9 (research + 7 features + backlog/report), each merged to `main`
  and pushed.
- **Live-verified:** CO alarm, condensation and leveling advisories fire and show
  in the companion + Comfort panel; scenes apply through safety; maintenance shows
  realistic due windows.

## What shipped

| # | Feature | Pain point | Backend | Bench | Product UI | Tests |
|---|---------|-----------|---------|-------|-----------|-------|
| 1 | **Air quality & safety** — CO, LPG, smoke, CO₂, humidity sensors + edge alarms (CO graduated warn/danger, gas leak, smoke, high-CO₂ ventilate, **condensation/mould via dew point**, **cabin-climate-extreme** for pets/pipes when parked) | CO deaths, damp/mould, pets | `plugins/air_quality`, 6 advisors in `notices.py` | Air & Safety card + scenarios | Comfort "Air & Safety" panel (threshold colours + pulsing alarm) | 8 |
| 2 | **Scenes / routines** — Goodnight, Good morning, Set up camp, Leaving | Nightly/daily repetition | `scenes.py` (safety-checked intent bundles) + spoken triggers | (acts on existing actuators) | Home "Routines" buttons | 6 |
| 3 | **Leveling assistant** — pitch/roll + "raise this side N cm" | Parking flat | `plugins/leveling` + `NotLevel` advisor + geometry helper | Leveling card | Journey bubble-level | 5 |
| 4 | **Propane / LPG level** | Cooking-gas runout | `plugins/propane` + `LowPropane` | Propane slider | Comfort propane gauge | 2 |
| 5 | **Maintenance reminders** — odometer + date, one-tap done | Upkeep drift | `maintenance.py` + `ServiceDue` advisor | (uses odometer) | Power "Maintenance" panel | 5 |
| 6 | **Fridge monitor** — temp, door-ajar, compressor draw | Food safety + draw | `plugins/fridge` + `FridgeWarm`/`FridgeDoorOpen` | temp slider + door toggle | Power fridge + draw gauges | 3 |
| 7 | **Security away-mode** — arm/disarm + intrusion alarm | Feeling unsafe | `security.py` + `Intrusion` advisor | door + motion toggles | Home "Away mode" panel | 3 |

All new sensors are edge-deterministic and offline-first; the AI only rewords the
facts. Safety-critical alarms (CO/gas/smoke) never touch a model (Rule 2). Scenes
run every step through the existing safety validator.

## Assumptions made (so you can veto them)

1. **Alarm thresholds** — CO warn 35 ppm / danger 70 ppm; gas 10% LEL; CO₂ 1500 ppm;
   condensation at humidity ≥60% with walls within 1.5 °C of the dew point; cabin
   extreme <3 °C or >30 °C. Reasonable per safety guidance; tune against real
   sensors before shipping (per "measure, don't guess").
2. **New sensors are bench-injected, not world-simulated.** CO/humidity/tilt/propane
   are *inputs* like battery SoC, so they live on the bench (their simulator), not in
   `simulation.py`. No physics faked.
3. **Scene setpoints are fixed defaults** (sleep 16 °C, comfort 20 °C). Binding
   Goodnight's temperature to the *learned preference* is backlogged.
4. **Spoken scene triggers are deliberately narrow** (e.g. "goodnight", "we're
   leaving") because a scene actuates devices — better to miss than to misfire.
5. **Leveling geometry** assumes a 2.0 m track / 3.6 m wheelbase for the cm figures.
6. **Maintenance intervals are generic** (engine 15 000 km, damp check yearly, alarm
   test 6-monthly) and odometer items baseline to the current interval window so a
   used van isn't instantly "overdue". User-editable intervals are backlogged.
7. **Research is search + domain knowledge, not a citation-grade survey** — this
   environment can't reach every forum; where real-world data is needed (dump
   stations, TPMS) the framework is built and the data integration backlogged.

## Deferred (see `backlog.md` → "Van-life pain points")

Connectivity/signal plugin, services-on-route (water/dump/LPG/fuel via OSM),
cost/trip stats, security/intrusion mode, solar-orientation & load-timing advisor,
fridge plugin, black/cassette tank, explicit pet mode, user-editable scenes &
maintenance intervals, air-quality trend logging. Each needs either hardware I can't
simulate meaningfully or an online data source blocked in this environment.

## Notes / caveats

- Overpass (camp/services real data) is unreachable from this sandbox, so the
  services-on-route idea stayed in the backlog rather than shipping half-working.
- The bench's Turbo Dash road only animates when its tab is foreground (Chrome
  throttles background `requestAnimationFrame`) — unrelated to this session, noted
  for anyone testing.
