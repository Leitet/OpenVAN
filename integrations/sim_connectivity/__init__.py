"""Connectivity Simulator — the world-sim provider for the van's uplink.

Provides the simulated internet link, network type, signal strength and GPS-fix
flag. Installed by default, removable — remove it (with no router integration,
e.g. Teltonika/Starlink) and connectivity honestly reads unknown. Offline-first
(Rule 3) is unaffected: Core never *depends* on these signals being present.
"""

from __future__ import annotations

from openvan_core import IntegrationInfo, Permissions, Status, Transport, WorldSimProvider


class SimConnectivity(WorldSimProvider):
    SEEDS = {
        "connectivity.online": True,
        "connectivity.network": "LTE",  # LTE | 5G | WiFi | Starlink | none
        "connectivity.signal_pct": 74.0,
        "connectivity.has_gps_fix": True,
    }

    info = IntegrationInfo(
        id="sim_connectivity",
        name="Connectivity Simulator",
        category="connectivity",
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
            "Provides the simulated internet link and signal strength. Remove it "
            "when a router integration (Teltonika, Starlink, …) provides these "
            "instead."
        ),
    )
