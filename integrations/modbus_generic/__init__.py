"""Generic Modbus RTU/TCP — the long-tail unlocker.

A huge amount of energy kit (inverters, chargers, BMS, AC meters, EPEver/EPsolar
MPPTs) speaks Modbus. A generic, register-mapped Modbus driver won't be as polished
as a native integration, but it turns "unsupported" into "works if you supply the
map" for a very long tail of devices. Local, offline, but read-mapping is fiddly —
hence `open` rather than `native`, and control is `limited`.

In simulation this driver models a generic **AC energy meter** on the shore/inverter
line, deriving apparent power from the inverter load so the register reads plausibly.
"""

from __future__ import annotations

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport


def _f(twin, key, default=0.0):
    try:
        return float(twin.get(key))
    except (TypeError, ValueError):
        return default


class ModbusGeneric(Integration):
    info = IntegrationInfo(
        id="modbus_generic",
        name="Generic Modbus RTU/TCP",
        category="energy",
        vendor="Generic",
        transports=[Transport.MODBUS_TCP, Transport.MODBUS_RTU],
        local=True,
        offline_capable=True,
        discovery="manual",
        permissions=Permissions(read=True, control="limited", configure=True),
        safety_class=3,
        status=Status.OPEN,
        priority="P0",
        provides=["ac_meter.power", "ac_meter.voltage"],
        description=(
            "Register-mapped Modbus over TCP or RTU/RS-485. Needs a device register "
            "map, but unlocks a long tail of inverters, chargers, meters and BMS."
        ),
        warning="Requires a per-device register map; readings are only as good as the map.",
    )

    async def simulate(self, dt: float) -> None:
        twin = self.twin
        on = bool(twin.get("inverter.on"))
        load = _f(twin, "inverter.ac_load") if on else 0.0
        await twin.set_signal("ac_meter.power", round(load, 1), source="modbus_generic")
        await twin.set_signal("ac_meter.voltage", 230.0 if on else 0.0, source="modbus_generic")
