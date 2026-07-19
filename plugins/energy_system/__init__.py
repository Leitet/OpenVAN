"""Energy system plugin — the DC power picture beyond the battery.

Where ``battery_monitor`` exposes the house battery and solar *power*, this plugin
surfaces the rest of the van's DC energy system as semantic entities: today's solar
**yield**, the **alternator** (DC-DC) charge while driving, **shore** power, and the
**inverter** (on/off + outlet temperature).

These are physical facts of the van. In simulation the environment layer
(``simulation.py``) evolves them; on a real van an energy integration (Victron GX,
Renogy, …) streams them in over its transport. Either way this plugin only *reads*
through the backend, so the same code runs against the twin today and real hardware
tomorrow.

Category: energy. Domain: energy_system.
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


# Raw twin signal  ->  semantic OpenVan entity. Booleans (shore/inverter) carry no
# unit; their state is the on/off value itself.
SENSORS = [
    _SensorMap("sensor.solar_yield_today", "Solar Yield Today", "solar.yield_today_wh", "Wh"),
    _SensorMap("sensor.alternator_power", "Alternator", "alternator.power", "W"),
    _SensorMap("binary_sensor.shore_power", "Shore Power", "shore.connected"),
    _SensorMap("switch.inverter", "Inverter", "inverter.on"),
    _SensorMap("sensor.inverter_temperature", "Inverter Temperature", "inverter.temperature", "°C"),
]


class EnergySystem(Plugin):
    domain = "energy_system"
    name = "Energy System"
    version = "0.1.0"
    categories = ["energy"]

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
                    category="energy",
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
