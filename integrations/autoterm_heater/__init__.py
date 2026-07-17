"""Autoterm diesel heater — realistic local heater control.

Autoterm (Planar) heaters are popular because, unlike Webasto/Eberspächer, their
serial protocol has been reverse-engineered by the community (VanPi / Pekaway) —
you can read status and set temperature over a local **UART** with no cloud. That
makes them the most realistic *controllable* heater for a launch integration, but
because the protocol is reverse-engineered and a heater is a combustion appliance,
this is a high-caution driver: safety class 3, control `limited`.

Heater control still goes through OpenVan's safety layer (battery load-shedding,
fuel-required rules) — this integration only bridges the protocol; it never
actuates around safety. In simulation it reflects the twin's diesel-heater state
and reports a flame/outlet temperature that rises when the heater is on.
"""

from __future__ import annotations

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport


def _f(twin, key, default=0.0):
    try:
        return float(twin.get(key))
    except (TypeError, ValueError):
        return default


class AutotermHeater(Integration):
    info = IntegrationInfo(
        id="autoterm_heater",
        name="Autoterm / Planar heater",
        category="climate",
        vendor="Autoterm",
        transports=[Transport.SERIAL],
        local=True,
        offline_capable=True,
        discovery="manual",
        permissions=Permissions(read=True, control="limited", configure=False),
        safety_class=3,
        status=Status.REVERSE_ENGINEERED,
        priority="P0",
        provides=["heater.autoterm.state", "heater.autoterm.outlet_temperature"],
        description=(
            "Autoterm/Planar diesel heater over a reverse-engineered local UART. "
            "Read status and set temperature offline — control via the safety layer."
        ),
        warning=(
            "Community-reverse-engineered serial protocol on a combustion appliance; "
            "control always passes through OpenVan's safety rules."
        ),
    )

    async def simulate(self, dt: float) -> None:
        twin = self.twin
        on = bool(twin.get("diesel_heater.on"))
        await twin.set_signal(
            "heater.autoterm.state", "heating" if on else "off", source="autoterm_heater"
        )
        # Outlet air is hot when running, near cabin temp when off.
        cabin = _f(twin, "cabin.temperature", 20.0)
        outlet = (cabin + 55.0) if on else cabin
        await twin.set_signal(
            "heater.autoterm.outlet_temperature", round(outlet, 1), source="autoterm_heater"
        )
