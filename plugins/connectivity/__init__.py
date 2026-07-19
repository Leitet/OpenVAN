"""Connectivity plugin — the van's link to the outside world.

Surfaces internet reachability, mobile signal strength, the active network type
and the GNSS fix as semantic entities. Connectivity is a first-class van-life
concern (you plan routes and overnight spots around coverage), but offline-first:
these are *status*, never a dependency — Core keeps working with no signal (Rule 3).

Like the energy system, connectivity is a physical fact of the van. In simulation
the bench drives it; on a real van a router/modem integration (Teltonika RutOS,
Starlink, a GL.iNet, …) reads it over its transport. This plugin only reads through
the backend, so the same code runs against the twin today and real hardware later.

Category: connectivity. Domain: connectivity.
"""

from __future__ import annotations

from dataclasses import dataclass

from openvan_core import Entity, Plugin


@dataclass
class _SensorMap:
    entity_id: str
    name: str
    signal: str
    unit: str | None = None


SENSORS = [
    _SensorMap("binary_sensor.internet", "Internet", "connectivity.online"),
    _SensorMap("sensor.signal_strength", "Signal", "connectivity.signal_pct", "%"),
    _SensorMap("sensor.network_type", "Network", "connectivity.network"),
    _SensorMap("binary_sensor.gps_fix", "GPS Fix", "connectivity.has_gps_fix"),
]


class Connectivity(Plugin):
    domain = "connectivity"
    name = "Connectivity"
    version = "0.1.0"
    categories = ["connectivity"]

    def __init__(self, hub, backend, config=None):
        super().__init__(hub, backend, config)
        self._unwatchers = []

    async def async_setup(self) -> None:
        for sensor in SENSORS:
            value = await self.backend.read(sensor.signal)
            domain = sensor.entity_id.split(".", 1)[0]
            await self.hub.register_entity(
                Entity(
                    entity_id=sensor.entity_id,
                    name=sensor.name,
                    domain=domain,
                    category="connectivity",
                    state=value,
                    unit=sensor.unit,
                )
            )
            self._unwatchers.append(self._watch(sensor))

    def _watch(self, sensor: _SensorMap):
        async def _on_change(_key: str, value) -> None:
            await self.hub.set_state(sensor.entity_id, value)

        return self.backend.watch(sensor.signal, _on_change)

    async def async_teardown(self) -> None:
        for unwatch in self._unwatchers:
            unwatch()
        self._unwatchers.clear()
