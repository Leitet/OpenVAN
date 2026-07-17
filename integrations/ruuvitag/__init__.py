"""RuuviTag — wireless BLE environment sensors.

RuuviTags broadcast temperature, humidity, pressure and battery in a documented
BLE advertisement — no pairing, no cloud, cheap, and popular for monitoring the
fridge, an outdoor probe, or a second cabin zone. Read-only by nature (they only
advertise), so this is a safety-class-0 sensor integration.

In simulation this driver models an **outdoor** tag, tracking the twin's outside
temperature plus a plausible humidity and a slowly-draining coin-cell battery.
"""

from __future__ import annotations

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport


def _f(twin, key, default=0.0):
    try:
        return float(twin.get(key))
    except (TypeError, ValueError):
        return default


class RuuviTag(Integration):
    info = IntegrationInfo(
        id="ruuvitag",
        name="RuuviTag (BLE)",
        category="sensors",
        vendor="Ruuvi",
        transports=[Transport.BLE],
        local=True,
        offline_capable=True,
        discovery="ble_scan",
        permissions=Permissions(read=True, control=False, configure=False),
        safety_class=0,
        status=Status.COMMUNITY,
        priority="P0",
        provides=[
            "ruuvitag.outdoor.temperature", "ruuvitag.outdoor.humidity",
            "ruuvitag.outdoor.battery",
        ],
        description=(
            "Battery BLE sensors broadcasting temperature/humidity/pressure. No "
            "pairing, no cloud — easy wireless monitoring of fridge or outdoor probe."
        ),
    )

    async def simulate(self, dt: float) -> None:
        twin = self.twin
        temp = _f(twin, "outside.temperature", 11.0)
        # Cooler air holds less absolute moisture at a given RH — keep it simple:
        rh = max(30.0, min(95.0, 70.0 - temp))
        await twin.set_signal("ruuvitag.outdoor.temperature", round(temp, 1), source="ruuvitag")
        await twin.set_signal("ruuvitag.outdoor.humidity", round(rh, 1), source="ruuvitag")
        # Coin-cell battery: report a healthy 2.9 V (drains far too slowly to model per-tick).
        await twin.set_signal("ruuvitag.outdoor.battery", 2.9, source="ruuvitag")
