"""Water system plugin — fresh/grey tanks and the water pump.

Sensors for both tanks plus a controllable pump. The pump declares a
``dry_run_signal`` so the ``PumpDryRunProtection`` safety rule refuses to run it
when the fresh tank is empty. It reads/writes only through the backend, so it
runs against the simulated van (the simulation engine moves water fresh -> grey
while the pump runs).

Category: water. Domain: water_system.
"""

from __future__ import annotations

from dataclasses import dataclass

from openvan_core import Entity, Plugin

PUMP_ENTITY = "switch.water_pump"
PUMP_SIGNAL = "water_pump.on"


@dataclass
class _SensorMap:
    entity_id: str
    name: str
    signal: str


TANKS = [
    _SensorMap("sensor.fresh_water_level", "Fresh Water", "fresh_water.level_pct"),
    _SensorMap("sensor.grey_water_level", "Grey Water", "grey_water.level_pct"),
    _SensorMap("sensor.cassette_level", "Toilet Cassette", "cassette.level_pct"),
]


class WaterSystem(Plugin):
    domain = "water_system"
    name = "Water System"
    version = "0.1.0"
    categories = ["water"]

    def __init__(self, hub, backend, config=None):
        super().__init__(hub, backend, config)
        self._unwatchers = []

    async def async_setup(self) -> None:
        for tank in TANKS:
            value = await self.backend.read(tank.signal)
            await self.hub.register_entity(
                Entity(
                    entity_id=tank.entity_id,
                    name=tank.name,
                    domain="sensor",
                    category="water",
                    state=value,
                    unit="%",
                )
            )
            self._unwatchers.append(self._watch(tank))

        is_on = bool(await self.backend.read(PUMP_SIGNAL, False))
        await self.hub.register_entity(
            Entity(
                entity_id=PUMP_ENTITY,
                name="Water Pump",
                domain="switch",
                category="water",
                state="on" if is_on else "off",
                controllable=True,
                commands=["turn_on", "turn_off"],
                attributes={
                    "essential": True,  # water is a base system; never load-shed
                    "dry_run_signal": "fresh_water.level_pct",
                },
            ),
            handler=self._handle_pump,
        )

    def _watch(self, tank: _SensorMap):
        async def _on_change(_key: str, value) -> None:
            await self.hub.set_state(tank.entity_id, value)

        return self.backend.watch(tank.signal, _on_change)

    async def _handle_pump(self, command: str, _params: dict) -> None:
        turn_on = command == "turn_on"
        await self.backend.write(PUMP_SIGNAL, turn_on)
        await self.hub.set_state(PUMP_ENTITY, "on" if turn_on else "off")

    async def async_teardown(self) -> None:
        for unwatch in self._unwatchers:
            unwatch()
        self._unwatchers.clear()
