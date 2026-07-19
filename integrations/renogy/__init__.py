"""Renogy — the common Victron alternative.

Renogy shunts, Rover/Wanderer MPPT controllers and DCC DC-DC chargers are the
budget alternative to Victron in the DIY market. They expose data over **Modbus
RTU (RS-485)**, **BLE** (the BT modules), and — for the ONE hub — a cloud API.
The local Modbus/BLE paths are community-documented and stable; the driver is
solid but not vendor-blessed, hence `community`.

In simulation this driver feeds the same normalised solar-yield signal as Victron
(off by default, so enabling it is a deliberate choice for a Renogy-based rig).
"""

from __future__ import annotations

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport


def _f(twin, key, default=0.0):
    try:
        return float(twin.get(key))
    except (TypeError, ValueError):
        return default


class Renogy(Integration):
    info = IntegrationInfo(
        id="renogy",
        name="Renogy",
        category="energy",
        vendor="Renogy",
        transports=[Transport.MODBUS_RTU, Transport.BLE],
        local=True,
        offline_capable=True,
        discovery="ble_scan",
        permissions=Permissions(read=True, control="limited", configure="limited"),
        safety_class=3,
        status=Status.COMMUNITY,
        priority="P1",
        provides=["solar.power", "house_battery.soc", "solar.controller_temperature"],
        description=(
            "Renogy shunt, Rover/Wanderer MPPT and DCC DC-DC over Modbus-RTU (RS-485) "
            "or BLE. The budget alternative to Victron for DIY builds."
        ),
    )

    async def simulate(self, dt: float) -> None:
        # Solar yield is world/environment state (the simulation owns it) — Renogy only
        # adds its *own* device reading: the MPPT controller's temperature.
        twin = self.twin
        base = _f(twin, "cabin.temperature", 20.0)
        bump = 12.0 * min(1.0, _f(twin, "solar.power") / 400.0)
        await twin.set_signal("solar.controller_temperature", round(base + bump, 1), source="renogy")
