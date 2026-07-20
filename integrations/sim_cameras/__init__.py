"""Cameras Simulator — the world-sim provider for the four reference cameras.

Provides the simulated rear/cabin/entry/awning cameras (online, no motion, not
recording). Installed by default, removable — remove it (with no real camera
integration) and the camera grid honestly reads unknown.
"""

from __future__ import annotations

from openvan_core import IntegrationInfo, Permissions, Status, Transport, WorldSimProvider

_CAMERAS = ("rear", "cabin", "entry", "awning")


class SimCameras(WorldSimProvider):
    SEEDS = {
        f"camera.{cam}.{measure}": measure == "online"
        for cam in _CAMERAS
        for measure in ("online", "motion", "recording")
    }

    info = IntegrationInfo(
        id="sim_cameras",
        name="Cameras Simulator",
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
            "Provides the four simulated cameras (rear, cabin, entry, awning). "
            "Remove it when a real camera integration provides these instead."
        ),
    )
