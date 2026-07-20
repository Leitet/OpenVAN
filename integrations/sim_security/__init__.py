"""Security Simulator — the world-sim provider for door/motion sensing.

Provides the simulated door and motion sensors (quiet by default). Installed by
default, removable — remove it (with no real sensors, e.g. BTHome/ESPHome door
and PIR sensors) and the security state honestly reads unknown.
"""

from __future__ import annotations

from openvan_core import IntegrationInfo, Permissions, Status, Transport, WorldSimProvider


class SimSecurity(WorldSimProvider):
    SEEDS = {
        "security.door_open": False,
        "security.motion": False,
    }

    info = IntegrationInfo(
        id="sim_security",
        name="Security Simulator",
        category="sensors",
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
            "Provides the simulated door and motion sensors. Remove it when real "
            "sensors (BTHome, ESPHome, …) provide these instead."
        ),
    )
