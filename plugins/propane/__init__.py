"""Propane / LPG bottle level plugin.

Cooking gas running out mid-meal — with no gauge and incompatible refill fittings
between countries — is a classic van annoyance (research #7). This exposes the
bottle level as a sensor; the `LowPropane` advisor warns in time to swap or refill.
It pairs with the air-quality `GasLeak` alarm (that watches for a *leak*; this
watches the *level*).

Read-only, backend-sourced (a real build reads a bottle scale or a level sensor).

Category: climate. Domain: propane.
"""

from __future__ import annotations

from openvan_core import Entity, Plugin

ENTITY_ID = "sensor.propane_level"
SIGNAL = "propane.level_pct"


class Propane(Plugin):
    domain = "propane"
    name = "Propane"
    version = "0.1.0"
    categories = ["climate"]

    def __init__(self, hub, backend, config=None):
        super().__init__(hub, backend, config)
        self._unwatch = None

    async def async_setup(self) -> None:
        value = await self.backend.read(SIGNAL, 60.0)
        entity = Entity(
            entity_id=ENTITY_ID,
            name="Propane",
            domain="sensor",
            category="climate",
            state=value,
            unit="%",
        )
        await self.hub.register_entity(entity)

        async def _on_change(_key: str, val) -> None:
            await self.hub.set_state(ENTITY_ID, val)

        self._unwatch = self.backend.watch(SIGNAL, _on_change)

    async def async_teardown(self) -> None:
        if self._unwatch is not None:
            self._unwatch()
            self._unwatch = None
