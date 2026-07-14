"""Cabin light plugin — a controllable actuator.

Demonstrates the command path: an intent (from AI, API or a button) is safety-
checked by Core, then this plugin drives the actuator by writing to the backend.
The write lands on the twin signal ``cabin_light.on``, which the simulator shows.

Marked non-essential, so the critical-battery load-shedding safety rule will
refuse to switch it on when the house battery is critically low.

Category: lighting. Domain: cabin_light.
"""

from __future__ import annotations

from openvan_core import Entity, Plugin

ENTITY_ID = "light.cabin"
SIGNAL = "cabin_light.on"


class CabinLight(Plugin):
    domain = "cabin_light"
    name = "Cabin Light"
    version = "0.1.0"
    categories = ["lighting"]

    async def async_setup(self) -> None:
        is_on = bool(await self.backend.read(SIGNAL, False))
        entity = Entity(
            entity_id=ENTITY_ID,
            name="Cabin Light",
            domain="light",
            category="lighting",
            state="on" if is_on else "off",
            controllable=True,
            commands=["turn_on", "turn_off"],
            attributes={"essential": False},
        )
        await self.hub.register_entity(entity, handler=self._handle_command)

    async def _handle_command(self, command: str, _params: dict) -> None:
        turn_on = command == "turn_on"
        await self.backend.write(SIGNAL, turn_on)
        await self.hub.set_state(ENTITY_ID, "on" if turn_on else "off")
