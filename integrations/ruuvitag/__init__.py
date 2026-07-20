"""RuuviTag — wireless BLE environment sensors.

RuuviTags broadcast temperature, humidity, pressure and battery in a documented
BLE advertisement — no pairing, no cloud, cheap, and popular for monitoring the
fridge, an outdoor probe, or a second cabin zone. Read-only by nature (they only
advertise), so this is a safety-class-0 sensor integration.

In simulation this driver models an **outdoor** tag, tracking the twin's outside
temperature plus a plausible humidity and a slowly-draining coin-cell battery.
"""

from __future__ import annotations

import struct

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport

RUUVI_MANUFACTURER_ID = 0x0499


def parse_rawv2(payload: bytes) -> dict[str, float] | None:
    """Ruuvi RAWv2 (format 5, officially documented): temp sint16*0.005 °C,
    humidity uint16*0.0025 %, pressure uint16+50000 Pa, …, power field packs
    battery mV ((v>>5)+1600) and TX power."""
    if len(payload) < 15 or payload[0] != 0x05:
        return None
    temp_raw, hum_raw, press_raw = struct.unpack(">hHH", payload[1:7])
    power = struct.unpack(">H", payload[13:15])[0]
    return {
        "temperature": round(temp_raw * 0.005, 2),
        "humidity": round(hum_raw * 0.0025, 2),
        "pressure_hpa": round((press_raw + 50000) / 100.0, 2),
        "battery": round(((power >> 5) + 1600) / 1000.0, 3),
    }


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._unsub = None

    async def async_setup(self) -> None:
        await super().async_setup()
        # Real tags via the shared BLE substrate (RAWv2 broadcasts); the sim
        # radio carries bench-injected frames through the same parser.
        if self.ble is not None:
            self._unsub = self.ble.subscribe(self._on_adv, manufacturer_id=RUUVI_MANUFACTURER_ID)
            self.live = getattr(self.ble, "plan", None) == "bleak"

    async def async_teardown(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        await super().async_teardown()

    async def _on_adv(self, adv) -> None:
        data = parse_rawv2(adv.manufacturer_data.get(RUUVI_MANUFACTURER_ID, b""))
        if data is None:
            return
        device = adv.address.replace(":", "").lower()[-4:] or "tag"
        for measure, value in data.items():
            await self.twin.set_signal(f"ruuvitag.{device}.{measure}", value, source=self.info.id)

    async def simulate(self, dt: float) -> None:
        twin = self.twin
        temp = _f(twin, "outside.temperature", 11.0)
        # Cooler air holds less absolute moisture at a given RH — keep it simple:
        rh = max(30.0, min(95.0, 70.0 - temp))
        await twin.set_signal("ruuvitag.outdoor.temperature", round(temp, 1), source="ruuvitag")
        await twin.set_signal("ruuvitag.outdoor.humidity", round(rh, 1), source="ruuvitag")
        # Coin-cell battery: report a healthy 2.9 V (drains far too slowly to model per-tick).
        await twin.set_signal("ruuvitag.outdoor.battery", 2.9, source="ruuvitag")
