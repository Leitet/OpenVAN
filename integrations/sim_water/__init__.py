"""Water & Tanks Simulator — the world-sim provider for tanks and fuels.

Provides fresh/grey water, the cassette, and the diesel/propane tank levels.
Installed by default, removable — remove it (with no real tank integration, e.g.
Mopeka pucks or SeeLevel) and the levels honestly become unknown. The pump
physics (fresh → grey while running) only evolves while this card is installed.
"""

from __future__ import annotations

from openvan_core import IntegrationInfo, Permissions, Status, Transport, WorldSimProvider


class SimWater(WorldSimProvider):
    SEEDS = {
        "fresh_water.level_pct": 55.0,
        "grey_water.level_pct": 8.0,
        "cassette.level_pct": 20.0,
        "diesel_tank.level_pct": 70.0,
        "propane.level_pct": 60.0,
    }

    info = IntegrationInfo(
        id="sim_water",
        name="Water & Tanks Simulator",
        category="water",
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
            "Provides the simulated water, cassette and fuel tank levels. Remove "
            "it when real tank sensors (Mopeka, SeeLevel, …) provide these instead."
        ),
    )
