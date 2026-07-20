# Writing an OpenVan plugin

Everything that touches the van is a plugin: sensors, lights, heaters, water,
batteries, connectivity. This guide shows the two patterns — a **sensor**
(read-only) and an **actuator** (controllable, safety-checked) — and how to keep
[Rule 1](../CLAUDE.md#rule-1--every-feature-must-work-against-the-twin): every
feature works against the twin — injectable from the Hardware Bench, visible in
the product UI.

## The shape of a plugin

A plugin is a Python package under `plugins/` whose `__init__.py` defines a
subclass of `openvan_core.Plugin`. It self-registers on import — no manifest, no
entry-point wiring for the monorepo.

```python
from openvan_core import Entity, Plugin

class MyPlugin(Plugin):
    domain = "my_plugin"        # unique id; required — this is what registers it
    name = "My Plugin"          # human name
    version = "0.1.0"
    categories = ["climate"]    # energy | lighting | climate | water | sensors | vehicle | connectivity

    async def async_setup(self) -> None:
        ...                     # register entities, subscribe to signals

    async def async_teardown(self) -> None:
        ...                     # unwatch / close (optional)
```

A plugin receives three things (`self.hub`, `self.backend`, `self.config`):

- `self.hub` — register entities, set states, (rarely) inspect other entities.
- `self.backend` — **the only way to touch hardware.** `read`, `write`, `watch`.
- `self.config` — a dict of per-plugin config (may be empty).

> **Never import a hardware library into a plugin and talk to it directly.** Go
> through `self.backend`. That indirection is exactly what makes the plugin run
> in the simulator today and on real hardware later.

## Pattern A — a sensor (read-only)

Map a raw twin signal to a semantic entity and keep it in sync. Full example:
[`plugins/battery_monitor/`](../plugins/battery_monitor/__init__.py).

```python
async def async_setup(self) -> None:
    value = await self.backend.read("cabin.humidity")
    await self.hub.register_entity(
        Entity(
            entity_id="sensor.cabin_humidity",
            name="Cabin Humidity",
            domain="sensor",
            category="sensors",
            state=value,
            unit="%",
        )
    )

    async def on_change(_key, new_value):
        await self.hub.set_state("sensor.cabin_humidity", new_value)

    self._unwatch = self.backend.watch("cabin.humidity", on_change)
```

## Pattern B — an actuator (controllable + safety)

Register a controllable entity with a command handler. The handler drives the
actuator by **writing a signal through the backend**. Full example:
[`plugins/cabin_light/`](../plugins/cabin_light/__init__.py).

```python
async def async_setup(self) -> None:
    await self.hub.register_entity(
        Entity(
            entity_id="switch.water_pump",
            name="Water Pump",
            domain="switch",
            category="water",
            state="off",
            controllable=True,
            commands=["turn_on", "turn_off"],
            attributes={"essential": True},   # see safety note below
        ),
        handler=self._handle,
    )

async def _handle(self, command: str, _params: dict) -> None:
    on = command == "turn_on"
    await self.backend.write("water_pump.on", on)
    await self.hub.set_state("switch.water_pump", "on" if on else "off")
```

Commands never reach your handler unless they pass the safety layer. Mark loads
that may be shed at critical battery with `attributes["essential"] = False`; mark
loads that must keep working (e.g. safety-critical) as `essential: True`.

### Adding a safety rule

Constraints live in `core/openvan_core/safety.py` as `SafetyRule`s (return a
`SafetyDecision`, or `None` when the rule doesn't apply). Register them in
`build_core` (`runtime.py`). Example built-in: `CriticalBatteryLoadShedding`.

## Rule 1 checklist — bench + product support

When your plugin introduces **new signal keys**, make them drivable/observable:

1. **Seed** a sensible default. Actuator rest-states (your plugin's own
   switches/setpoints) go in `Config.seed_twin`
   (`core/openvan_core/config.py`). *World* data the environment would measure
   (a tank level, a temperature) belongs to a **world-sim provider card**
   instead — extend an existing `integrations/sim_*` provider's `SEEDS`, or add
   a new `WorldSimProvider` for a new domain (see
   [DRIVERS.md](DRIVERS.md#world-sim-providers--simulated-data-sources-as-drivers)),
   so removing the card honestly makes your entities read unknown.
2. **Inject** — automatic: every twin signal appears in the bench's **Signal
   browser** (grouped by source) the moment it exists. Add a hand-crafted
   `SignalSlider`/scenario to `bench/src/BenchApp.tsx` only when the signal
   deserves a curated experience (a drive dash, a one-click scenario).
3. **Observe** — in the **product UI** (`ui/`) add a `Gauge` (sensors) or a
   control/indicator (actuators) so the effect is visible where users look.
   If the domain can be unprovided on a real van, show `NoSource` when its
   signals are all `null` (see `ui/src/components/NoSource.tsx`).
4. **Test** — add a test in `core/tests/` that drives the twin and asserts the
   entity/behaviour, mirroring `test_core.py`.

## Test it

```python
# core/tests/test_my_plugin.py
from openvan_core import build_core

async def test_humidity_follows_twin():
    core = build_core()
    await core.start()
    await core.twin.set_signal("cabin.humidity", 61.0)
    assert core.hub.get_entity("sensor.cabin_humidity").state == 61.0
    await core.stop()
```

Run `pytest` in `core/`. Green means your plugin works against the simulated van.
