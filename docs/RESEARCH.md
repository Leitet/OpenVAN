# Van-life pain points → OpenVan features

A synthesis of what everyday van dwellers actually struggle with, drawn from van
communities and buyer/owner guides (r/vandwellers & r/vanlife threads, Two
Wandering Soles, Beyond the Bucket List, FarOutRide, Gnomad Home, Bearfoot Theory,
KombiLife, RV Life, nidirect/CO-safety guidance, Simarine Pico feature set), plus
the apps people lean on (Park4Night, iOverlander, Campercontact). This is the map
that drives the autonomous build — each pain point is scored for how well OpenVan
can help *from software on a ~$20 gateway*, then either built now or backlogged.

> **Method note / assumption.** This environment can't reach every forum directly,
> so the list blends live web search with well-established domain knowledge. It is
> meant as a working prioritisation, not a citation-grade survey. Where a feature
> needs real-world data we can't fetch offline (dump-station databases, TPMS
> hardware), the *framework* is built against the twin and the real integration is
> backlogged.

## The pain points

| # | Pain point | Frequency | OpenVan leverage | Status |
|---|------------|-----------|------------------|--------|
| 1 | **Power anxiety** — running out of battery, flying blind on draw, load management | Very high | High — we own battery + telemetry + predictions | Partly shipped (monitor, ETAs); enhanced |
| 2 | **Carbon monoxide / gas / fire** — CO from heaters & propane, leaks, sleeping with a heater on | High (life-critical) | High — sensors + edge alarms in <200 ms | **Built this session** |
| 3 | **Condensation, damp & mould** — moisture on cold surfaces, winter humidity | Very high | High — dew-point math over humidity + surface temp | **Built this session** |
| 4 | **Finding a place to sleep** — legal, safe, quiet spots | Very high | High — camp sources + AI micro-siting | Shipped (camp system) |
| 5 | **Water** — running out of fresh, grey/black overflow, finding refill/dump | High | Medium-High — tanks + ETAs + amenity-aware camps | Shipped + resource-aware camps |
| 6 | **Leveling** — parking flat for sleep & fridge | High | High — inclinometer + "raise this corner Ncm" | **Built this session** |
| 7 | **Cooking-gas (LPG/propane) runout** — no warning, hard to refill abroad | Medium-High | Medium — level sensor + low advisor | **Built this session** |
| 8 | **Comfort routines** — nightly "everything off + heater to sleep temp", morning wake | High (ergonomics) | High — safety-checked scene bundles + voice | **Built this session** |
| 9 | **Pets & pipes in extreme cabin temps** — parked van overheats/freezes | Medium (critical when it bites) | High — climate-extreme alarm when parked | **Built this session** |
| 10 | **Maintenance & mechanical** — service overdue, leaks, tyres | High | Medium — odometer/date reminders + log | Built if time / backlog |
| 11 | **Internet / connectivity** — signal, data caps, remote work | High | Medium — status + signal-aware hints | Backlog (needs modem integration) |
| 12 | **Trip planning for a tall/heavy van** — services en route, low bridges | Medium | Medium — routing exists; services layer needed | Backlog (needs data) |
| 13 | **Cost tracking** — fuel, camps, budget | Medium | Medium — telemetry + journal | Backlog |
| 14 | **Security / intrusion** — break-ins, feeling unsafe | Medium | Medium — motion/door sensors + alerts | Backlog (needs sensors) |
| 15 | **Solar optimisation** — when to run big loads, park for sun | Medium | High — we already have a solar forecast | Backlog (advisor on top of forecast) |
| 16 | **Fridge management** — draw, door-ajar, food safety | Medium | Medium — sensor + advisor | Backlog |
| 17 | **Black/cassette toilet** — full, find dump | Medium | Medium — mirror grey tank | Backlog |
| 18 | **Community & spot sharing / reviews** | Medium | Low (cloud/social, off-thesis) | Backlog |

## Design stance for the build

- **Physics before code (CLAUDE.md).** Safety alarms are edge-triggered deterministic
  thresholds — no model in the danger path (matches the existing safety layer and
  Rule 2). CO/gas/smoke must fire in <200 ms locally; that's the whole point of the
  edge gateway.
- **Offline-first (Rule 3).** Every new advisor/plugin is pure local state. The AI
  only *rewords* the same facts.
- **Rule 1.** Each feature is exercised from the Hardware Bench (raw signal
  injection) and surfaced in the product UI, with tests against the twin.
- **Simulator.** New sensors (air quality, inclinometer, propane) are *sensor*
  inputs — injected from the bench like battery SoC and solar, not world-physics —
  so no `simulation.py` change is required; bench sliders/scenarios are their sim.

See `docs/AUTONOMOUS_SESSION_REPORT.md` for exactly what shipped, and `backlog.md`
for everything deferred.
