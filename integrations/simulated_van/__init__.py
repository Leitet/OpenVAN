"""Built-in simulator — the catalog face of the environment physics.

Represents OpenVan's environment simulation as an "integration" so it appears in
the catalog alongside real ecosystems, and so it has an honest switch: toggling
this card on/off maps to ``Config.simulate`` — pausing/resuming the world physics
(battery, thermal, water, driving). It is never uninstalled (built-in), and it
injects nothing itself — the twin + :class:`VanSimulation` drive the core signals.

Pausing it does **not** stop per-driver sim modes: those keep ticking so a real
van can trial a driver in sim mode next to live hardware (mixed mode).
"""

from __future__ import annotations

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport


class SimulatedVan(Integration):
    info = IntegrationInfo(
        id="simulated_van",
        name="OpenVan Simulator",
        category="sensors",
        vendor="OpenVan",
        transports=[Transport.NATIVE_API],
        local=True,
        offline_capable=True,
        discovery="builtin",
        permissions=Permissions(read=True, control=True, configure=True),
        safety_class=0,
        status=Status.NATIVE,
        priority="P0",
        provides=[
            "house_battery.soc", "solar.power", "fresh_water.level_pct",
            "grey_water.level_pct", "cabin.temperature", "gps.lat", "gps.lon",
        ],
        description=(
            "The built-in environment simulation: evolves the reference van's world "
            "(battery, thermal, water, driving) so every feature works with no "
            "hardware. Pause it on a real van — drivers set to sim mode keep "
            "working, so you can still trial hardware you don't own yet."
        ),
    )
