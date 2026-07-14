"""Diesel heater plugin — a climate actuator.

Exposes ``climate.diesel_heater`` with on/off and a temperature setpoint. A
diesel heater is a high-draw load on start-up (glow plug) and obviously needs
diesel to run, so it is a good exercise of the safety layer:

* non-essential + high start-up load  -> blocked by ``CriticalBatteryLoadShedding``
* declares a ``fuel_signal``           -> blocked by ``FuelRequiredToStart``

It reads/writes only through the backend, so it runs against the simulated van.

Category: climate. Domain: diesel_heater.
"""

from __future__ import annotations

from openvan_core import Entity, Plugin

ENTITY_ID = "climate.diesel_heater"
SIG_ON = "diesel_heater.on"
SIG_SETPOINT = "diesel_heater.setpoint"
SIG_POWER = "diesel_heater.power"

# Electrical draw of the fan + fuel pump while running (watts). Start-up glow
# plug draw is higher but brief; modelled simply here.
RUNNING_POWER = 35.0
MIN_SETPOINT = 5.0
MAX_SETPOINT = 30.0


class DieselHeater(Plugin):
    domain = "diesel_heater"
    name = "Diesel Heater"
    version = "0.1.0"
    categories = ["climate"]

    async def async_setup(self) -> None:
        is_on = bool(await self.backend.read(SIG_ON, False))
        setpoint = float(await self.backend.read(SIG_SETPOINT, 20.0))
        entity = Entity(
            entity_id=ENTITY_ID,
            name="Diesel Heater",
            domain="climate",
            category="climate",
            state="heating" if is_on else "off",
            unit="°C",
            controllable=True,
            commands=["turn_on", "turn_off", "set_temperature"],
            attributes={
                "essential": False,
                "setpoint": setpoint,
                # Read by the FuelRequiredToStart safety rule.
                "fuel_signal": "diesel_tank.level_pct",
            },
        )
        await self.hub.register_entity(entity, handler=self._handle_command)

    async def _handle_command(self, command: str, params: dict) -> None:
        if command == "set_temperature":
            await self._set_temperature(params)
            return
        turn_on = command == "turn_on"
        await self.backend.write(SIG_ON, turn_on)
        await self.backend.write(SIG_POWER, RUNNING_POWER if turn_on else 0.0)
        await self.hub.set_state(ENTITY_ID, "heating" if turn_on else "off")

    async def _set_temperature(self, params: dict) -> None:
        try:
            target = float(params.get("temperature"))
        except (TypeError, ValueError):
            return
        target = max(MIN_SETPOINT, min(MAX_SETPOINT, target))
        await self.backend.write(SIG_SETPOINT, target)
        entity = self.hub.get_entity(ENTITY_ID)
        await self.hub.set_state(ENTITY_ID, entity.state, attributes={"setpoint": target})
