"""Vehicle & GPS Simulator — the world-sim provider for the moving van.

Provides GPS position, speed/heading/odometer, ignition and the road-limit
signals. Installed by default, removable — remove it (with no real vehicle
integration, e.g. OBD-II via WiCAN or a GPS/router feed) and the vehicle data
honestly becomes unknown. The driving physics (dead reckoning / road snapping)
only evolves while this card is installed.
"""

from __future__ import annotations

from openvan_core import IntegrationInfo, Permissions, Status, Transport, WorldSimProvider


class SimVehicle(WorldSimProvider):
    SEEDS = {
        # Parked in the Dolomites.
        "gps.lat": 46.5405,
        "gps.lon": 11.6553,
        "vehicle.speed_kmh": 0.0,
        "vehicle.heading": 90.0,
        "vehicle.odometer_km": 48210.0,
        "vehicle.ignition": False,
        "vehicle.trip_seconds": 0.0,
        "road.max_height_m": 0.0,
        "road.max_weight_t": 0.0,
        "road.max_width_m": 0.0,
    }

    info = IntegrationInfo(
        id="sim_vehicle",
        name="Vehicle & GPS Simulator",
        category="vehicle",
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
            "Provides the simulated GPS, speed, odometer and road limits — the "
            "van you can drive from the bench. Remove it when a real vehicle "
            "integration (OBD-II/WiCAN, router GPS, …) provides these instead."
        ),
    )
