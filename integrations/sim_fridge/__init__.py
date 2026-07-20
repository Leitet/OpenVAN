"""Fridge Simulator — the world-sim provider for the compressor fridge.

Provides the simulated fridge temperature, door state and power draw. Installed
by default, removable — remove it (with no real fridge integration, e.g. a
Dometic CFX3 / BLE fridge driver) and the fridge honestly reads unknown.
"""

from __future__ import annotations

from openvan_core import IntegrationInfo, Permissions, Status, Transport, WorldSimProvider


class SimFridge(WorldSimProvider):
    SEEDS = {
        # Cold, closed, drawing a typical compressor load.
        "fridge.temp_c": 4.0,
        "fridge.door_open": False,
        "fridge.power": 45.0,
    }

    info = IntegrationInfo(
        id="sim_fridge",
        name="Fridge Simulator",
        category="energy",
        vendor="OpenVan",
        transports=[Transport.NATIVE_API],
        local=True,
        offline_capable=True,
        discovery="builtin",
        permissions=Permissions(read=True, control=False, configure=False),
        safety_class=0,
        status=Status.NATIVE,
        priority="P0",
        provides=sorted(SEEDS),
        description=(
            "Provides the simulated compressor fridge (temperature, door, power "
            "draw). Remove it when a real fridge integration (CFX3, BLE fridges, "
            "…) provides these instead."
        ),
    )
