"""Teltonika RutOS — the connectivity gateway.

Teltonika RUTX routers are the de-facto internet/GPS/system gateway in serious van
builds: dual-SIM LTE, Wi-Fi, GPS, and a documented local Web/JSON API (plus SNMP
and MQTT). One integration surfaces signal strength, network type, data usage and
a GNSS fix — everything the "weak signal, better spot 300 m back" hint needs.

In simulation this driver reports a plausible LTE connection with signal strength
that dips a little while moving, and mirrors the vehicle GPS fix.
"""

from __future__ import annotations

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport


def _f(twin, key, default=0.0):
    try:
        return float(twin.get(key))
    except (TypeError, ValueError):
        return default


class TeltonikaRouter(Integration):
    info = IntegrationInfo(
        id="teltonika_router",
        name="Teltonika RutOS",
        category="connectivity",
        vendor="Teltonika Networks",
        transports=[Transport.HTTP, Transport.MQTT],
        local=True,
        offline_capable=True,
        discovery="dhcp",
        permissions=Permissions(read=True, control="limited", configure=True),
        safety_class=1,
        status=Status.OPEN,
        priority="P0",
        provides=[
            "connectivity.online", "connectivity.network",
            "connectivity.signal_pct", "connectivity.has_gps_fix",
        ],
        description=(
            "RUTX dual-SIM LTE / Wi-Fi / GPS gateway over the local RutOS Web API. "
            "Surfaces signal strength, network type and a GNSS fix."
        ),
    )

    async def simulate(self, dt: float) -> None:
        twin = self.twin
        moving = _f(twin, "vehicle.speed_kmh") > 0
        # Signal is steady when parked, a bit lower and choppier while moving.
        signal = 62.0 if moving else 78.0
        await twin.set_signal("connectivity.online", True, source="teltonika_router")
        await twin.set_signal("connectivity.network", "LTE", source="teltonika_router")
        await twin.set_signal("connectivity.signal_pct", signal, source="teltonika_router")
        has_fix = twin.get("gps.lat") is not None
        await twin.set_signal("connectivity.has_gps_fix", bool(has_fix), source="teltonika_router")
