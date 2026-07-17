"""Air quality & safety plugin — the sensors that keep a van habitable.

Carbon monoxide, LPG/propane, smoke, cabin humidity and CO2 as read-only OpenVan
entities. This is the *sensor* half of van safety; the alarms that act on it live
in the deterministic advisor layer (`notices.py`) so they fire in <200 ms on the
edge, no model in the danger path (physics before code, Rule 2).

Why it matters: CO from a diesel/propane heater or a running engine is the single
deadliest van-life hazard — odourless, and a small sealed cabin fills fast. High
humidity on cold walls is the most *common* one: condensation → damp → mould.

Reads everything through the backend, so it runs against the simulated van today
and a real CO/CO2/humidity sensor (I2C/Modbus) backend later.

Category: sensors. Domain: air_quality.
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


# Raw twin signal  ->  semantic OpenVan entity.
SENSORS = [
    _SensorMap("sensor.co", "Carbon Monoxide", "air.co_ppm", "ppm"),
    _SensorMap("sensor.lpg", "LPG / Propane", "air.lpg_pct_lel", "%LEL"),
    _SensorMap("sensor.co2", "CO₂", "air.co2_ppm", "ppm"),
    _SensorMap("sensor.cabin_humidity", "Cabin Humidity", "cabin.humidity_pct", "%"),
    _SensorMap("sensor.smoke", "Smoke", "air.smoke", ""),
]


class AirQuality(Plugin):
    domain = "air_quality"
    name = "Air Quality & Safety"
    version = "0.1.0"
    categories = ["sensors"]

    def __init__(self, hub, backend, config=None):
        super().__init__(hub, backend, config)
        self._unwatchers = []

    async def async_setup(self) -> None:
        for sensor in SENSORS:
            value = await self.backend.read(sensor.signal)
            entity = Entity(
                entity_id=sensor.entity_id,
                name=sensor.name,
                domain="sensor",
                category="safety",
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
