"""Climate & Air Simulator — the world-sim provider for the thermal world.

Provides cabin/outside temperature, humidity, air quality (CO, CO2, LPG, smoke)
and the level sensor. Installed by default, removable — remove it (with no real
climate sensors, e.g. RuuviTag/BTHome/ESPHome) and the readings honestly become
unknown. The thermal physics (heater warms the cabin, cabin loses heat outside)
only evolves while this card is installed.
"""

from __future__ import annotations

from openvan_core import IntegrationInfo, Permissions, Status, Transport, WorldSimProvider


class SimClimate(WorldSimProvider):
    SEEDS = {
        "cabin.temperature": 19.5,
        "outside.temperature": 11.0,
        "cabin.humidity_pct": 55.0,
        "air.co_ppm": 0.0,
        "air.lpg_pct_lel": 0.0,
        "air.co2_ppm": 600.0,
        "air.smoke": False,
        "imu.pitch_deg": 0.0,
        "imu.roll_deg": 0.0,
    }

    info = IntegrationInfo(
        id="sim_climate",
        name="Climate & Air Simulator",
        category="climate",
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
            "Provides the simulated cabin climate, air quality and leveling. "
            "Remove it when real sensors (RuuviTag, BTHome, ESPHome nodes, …) "
            "provide these instead."
        ),
    )
