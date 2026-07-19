"""Teltonika RutOS — the connectivity gateway.

Teltonika RUTX routers are the de-facto internet/GPS/system gateway in serious van
builds: dual-SIM LTE, Wi-Fi, GPS, and a documented local Web/JSON API (plus SNMP
and MQTT). One integration surfaces signal strength, network type, data usage and
a GNSS fix — everything the "weak signal, better spot 300 m back" hint needs.

Connectivity is core van state (the `connectivity.*` signals the simulation and
bench drive, surfaced by the connectivity plugin); this driver *reads* it from a
real router — so in sim it has nothing to fabricate. On real hardware its
``run_transport()`` will poll the RutOS Web API and stream signal/network/GPS in.
"""

from __future__ import annotations

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport


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

    # No simulate(): connectivity is core van state driven by the simulation/bench;
    # on real hardware run_transport() will stream the RutOS readings instead.
