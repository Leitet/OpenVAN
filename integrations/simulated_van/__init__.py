"""Built-in simulator — the reference integration.

Represents OpenVan's own digital twin as an "integration" so it appears in the
catalog alongside real ecosystems. It's always on, purely read-only, and injects
nothing itself — the twin + environment simulation already drive the core signals
(battery, water, climate, GPS). It exists so a fresh install shows a fully working,
honestly-labelled data source out of the box (safety class 0, native).
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
            "The built-in digital twin. Drives the reference van's raw signals so "
            "every feature works with no hardware attached."
        ),
    )
