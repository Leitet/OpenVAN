"""Fridge plugin — temperature, door and compressor draw.

The 12 V compressor fridge is a van's biggest steady load and its food-safety
weak point: a door left ajar on a bumpy track quietly warms everything and drains
the battery. This exposes the fridge's temperature, door state and power draw as
sensors; `FridgeWarm` and `FridgeDoorOpen` advisors do the nagging.

Read-only, backend-sourced (a real build reads the fridge's NTC + a door reed
switch + the shunt). Category: energy. Domain: fridge.
"""

from __future__ import annotations

from dataclasses import dataclass

from openvan_core import Entity, Plugin


@dataclass
class _SensorMap:
    entity_id: str
    name: str
    signal: str
    unit: str


SENSORS = [
    _SensorMap("sensor.fridge_temp", "Fridge Temp", "fridge.temp_c", "°C"),
    _SensorMap("sensor.fridge_power", "Fridge Draw", "fridge.power", "W"),
    _SensorMap("binary_sensor.fridge_door", "Fridge Door", "fridge.door_open", ""),
]


class Fridge(Plugin):
    domain = "fridge"
    name = "Fridge"
    version = "0.1.0"
    categories = ["energy"]

    def __init__(self, hub, backend, config=None):
        super().__init__(hub, backend, config)
        self._unwatchers = []

    async def async_setup(self) -> None:
        for sensor in SENSORS:
            value = await self.backend.read(sensor.signal)
            entity = Entity(
                entity_id=sensor.entity_id,
                name=sensor.name,
                domain=sensor.entity_id.split(".")[0],
                category="energy",
                state=value,
                unit=sensor.unit,
            )
            await self.hub.register_entity(entity)
            self._unwatchers.append(self._watch(sensor))

    def _watch(self, sensor: _SensorMap):
        async def _on_change(_key: str, value) -> None:
            await self.hub.set_state(sensor.entity_id, value)

        return self.backend.watch(sensor.signal, _on_change)

    async def async_teardown(self) -> None:
        for unwatch in self._unwatchers:
            unwatch()
        self._unwatchers.clear()
