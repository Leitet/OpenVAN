"""Victron Venus OS / GX — the flagship energy integration.

A Cerbo GX (or any Venus OS device) exposes the whole energy system over local
**MQTT** and **Modbus-TCP**; individual products also speak **VE.Direct** over
USB. This is the single highest-value integration — one connection covers the
battery monitor, MPPT solar, DC-DC/alternator, shore charger and inverter.

In simulation this driver injects the *normalised energy signals* a GX would
publish that the bare twin doesn't already drive: solar yield-so-far, alternator
charge while driving, shore state, and inverter telemetry. Real hardware fills the
same keys from live MQTT topics — the plugins above never know the difference.
"""

from __future__ import annotations

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport


def _f(twin, key, default=0.0):
    try:
        return float(twin.get(key))
    except (TypeError, ValueError):
        return default


class VictronVenus(Integration):
    info = IntegrationInfo(
        id="victron_venus",
        name="Victron Venus OS / GX",
        category="energy",
        vendor="Victron Energy",
        transports=[Transport.MQTT, Transport.MODBUS_TCP, Transport.VE_DIRECT],
        local=True,
        offline_capable=True,
        discovery="mdns",
        permissions=Permissions(read=True, control=True, configure="limited"),
        safety_class=3,  # can switch the inverter / set charge limits
        status=Status.NATIVE,
        priority="P0",
        provides=[
            "solar.yield_today_wh", "alternator.power", "shore.connected",
            "inverter.on", "inverter.ac_load", "inverter.temperature",
        ],
        description=(
            "Cerbo GX / Venus OS over local MQTT + Modbus-TCP. Covers battery, "
            "MPPT solar, DC-DC, shore charger and inverter in one connection."
        ),
    )

    async def simulate(self, dt: float) -> None:
        twin = self.twin
        # Accumulate today's solar yield from instantaneous PV power (Wh).
        yield_wh = _f(twin, "solar.yield_today_wh") + _f(twin, "solar.power") * dt / 3600.0
        await twin.set_signal("solar.yield_today_wh", round(yield_wh, 1), source="victron_venus")

        # The alternator charges hard while the engine runs, nothing when parked.
        driving = bool(twin.get("vehicle.ignition")) and _f(twin, "vehicle.speed_kmh") > 0
        await twin.set_signal("alternator.power", 720.0 if driving else 0.0, source="victron_venus")

        # Shore power: connected only when explicitly plugged in (bench signal).
        await twin.set_signal("shore.connected", bool(twin.get("shore.connected")), source="victron_venus")

        # Inverter telemetry — warm a little under load, idle otherwise.
        on = bool(twin.get("inverter.on"))
        ac_load = _f(twin, "inverter.ac_load") if on else 0.0
        base = _f(twin, "cabin.temperature", 20.0)
        temp = base + (18.0 * ac_load / 2000.0 if on else 0.0)
        await twin.set_signal("inverter.temperature", round(temp, 1), source="victron_venus")
