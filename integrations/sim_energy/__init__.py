"""Battery & Energy Simulator — the world-sim provider for the DC system.

"Everything is an integration": the reference van's battery, solar and DC-system
data exists because this card provides it. Installed by default, removable —
remove it (with no real energy integration installed) and the energy readings
honestly become unknown. The environment physics only evolves the energy domain
while this provider is installed. Replace it with Victron / a BLE BMS / EPEver
when you have real hardware — or keep both and let the real one own the signals.
"""

from __future__ import annotations

from openvan_core import IntegrationInfo, Permissions, Status, Transport, WorldSimProvider


class SimEnergy(WorldSimProvider):
    SEEDS = {
        "house_battery.soc": 82.0,
        "house_battery.voltage": 12.9,
        "house_battery.current": -4.2,
        "solar.power": 240.0,
        "solar.yield_today_wh": 0.0,
        "shore.connected": False,
        "inverter.on": False,
        "inverter.ac_load": 0.0,
        "inverter.temperature": 19.5,
        "alternator.power": 0.0,
    }

    info = IntegrationInfo(
        id="sim_energy",
        name="Battery & Energy Simulator",
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
            "Provides the simulated house battery, solar and DC system (shore, "
            "inverter, alternator). Remove it when a real energy integration "
            "(Victron, BLE BMS, EPEver…) provides these instead."
        ),
    )
