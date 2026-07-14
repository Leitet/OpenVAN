"""Vehicle plugin — GPS, speed, heading, odometer, ignition.

The van's motion is external input, like a real OBD-II / GPS feed, so these are
read-only sensors. In simulation the values are driven by the environment engine
(dead-reckoning from speed + heading) and the simulator's drive controls. This
is the foundation for journey advisors, weather-by-location and travel memory.

Category: vehicle. Domain: vehicle.
"""

from __future__ import annotations

from dataclasses import dataclass

from openvan_core import Entity, Plugin


@dataclass
class _SensorMap:
    entity_id: str
    name: str
    signal: str
    unit: str | None


SENSORS = [
    _SensorMap("sensor.vehicle_speed", "Speed", "vehicle.speed_kmh", "km/h"),
    _SensorMap("sensor.vehicle_heading", "Heading", "vehicle.heading", "°"),
    _SensorMap("sensor.odometer", "Odometer", "vehicle.odometer_km", "km"),
    _SensorMap("sensor.gps_latitude", "GPS Latitude", "gps.lat", "°"),
    _SensorMap("sensor.gps_longitude", "GPS Longitude", "gps.lon", "°"),
]


class Vehicle(Plugin):
    domain = "vehicle"
    name = "Vehicle"
    version = "0.1.0"
    categories = ["vehicle"]

    def __init__(self, hub, backend, config=None):
        super().__init__(hub, backend, config)
        self._unwatchers = []

    async def async_setup(self) -> None:
        for sensor in SENSORS:
            value = await self.backend.read(sensor.signal)
            await self.hub.register_entity(
                Entity(
                    entity_id=sensor.entity_id,
                    name=sensor.name,
                    domain="sensor",
                    category="vehicle",
                    state=value,
                    unit=sensor.unit,
                )
            )
            self._unwatchers.append(self._watch(sensor.entity_id, sensor.signal))

        ignition = bool(await self.backend.read("vehicle.ignition", False))
        await self.hub.register_entity(
            Entity(
                entity_id="sensor.ignition",
                name="Ignition",
                domain="sensor",
                category="vehicle",
                state="on" if ignition else "off",
            )
        )
        self._unwatchers.append(self._watch_ignition())

    def _watch(self, entity_id: str, signal: str):
        async def _on_change(_key: str, value) -> None:
            await self.hub.set_state(entity_id, value)

        return self.backend.watch(signal, _on_change)

    def _watch_ignition(self):
        async def _on_change(_key: str, value) -> None:
            await self.hub.set_state("sensor.ignition", "on" if value else "off")

        return self.backend.watch("vehicle.ignition", _on_change)

    async def async_teardown(self) -> None:
        for unwatch in self._unwatchers:
            unwatch()
        self._unwatchers.clear()
