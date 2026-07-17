"""Leveling plugin — an inclinometer for parking flat.

Sleeping on a slope is miserable and a tilted absorption fridge can be damaged, so
"am I level, and which ramp do I nudge?" is one of the most-wanted van gadgets
(the Simarine Pico sells partly on its pitch/roll readout). This exposes the van's
inclination as two sensors; the `NotLevel` advisor turns them into "raise the left
side ~4 cm" guidance.

Read-only, backend-sourced (a real build reads an MPU-6050/accelerometer). Sign
convention: pitch > 0 = nose up (front high); roll > 0 = right side low.

Category: vehicle. Domain: leveling.
"""

from __future__ import annotations

from dataclasses import dataclass

from openvan_core import Entity, Plugin


@dataclass
class _SensorMap:
    entity_id: str
    name: str
    signal: str


SENSORS = [
    _SensorMap("sensor.pitch", "Pitch", "imu.pitch_deg"),
    _SensorMap("sensor.roll", "Roll", "imu.roll_deg"),
]


class Leveling(Plugin):
    domain = "leveling"
    name = "Leveling"
    version = "0.1.0"
    categories = ["vehicle"]

    def __init__(self, hub, backend, config=None):
        super().__init__(hub, backend, config)
        self._unwatchers = []

    async def async_setup(self) -> None:
        for sensor in SENSORS:
            value = await self.backend.read(sensor.signal, 0.0)
            entity = Entity(
                entity_id=sensor.entity_id,
                name=sensor.name,
                domain="sensor",
                category="vehicle",
                state=value,
                unit="°",
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
