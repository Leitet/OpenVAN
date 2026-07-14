"""Battery monitor plugin — energy sensors.

Exposes the van's house-battery and solar telemetry as OpenVan entities. It reads
everything through the backend, so it runs unchanged against the simulator today
and against a real Victron/Modbus backend later.

Category: energy. Domain: battery_monitor.
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
    _SensorMap("sensor.house_battery_soc", "House Battery", "house_battery.soc", "%"),
    _SensorMap("sensor.house_battery_voltage", "Battery Voltage", "house_battery.voltage", "V"),
    _SensorMap("sensor.house_battery_current", "Battery Current", "house_battery.current", "A"),
    _SensorMap("sensor.solar_power", "Solar Power", "solar.power", "W"),
]


class BatteryMonitor(Plugin):
    domain = "battery_monitor"
    name = "Battery Monitor"
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
                domain="sensor",
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
