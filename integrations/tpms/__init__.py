"""BLE TPMS — the cheap valve-cap tire-pressure sensors ("TPMSII" type A).

The 1000+-post community thread's answer to tire monitoring: universal BLE
valve-cap sensors that broadcast pressure/temperature/battery. This driver parses
the most common format (manufacturer id 0x0100, 16 bytes, sensor id in bytes 0–5,
then ``<iib?``: pressure µbar·10, temperature c°C, battery %, alarm) — per the
`tpms_ble` community parser. Other families (SYTPMS, Michelin, …) can join the
same driver later.

Passive listener on the shared BLE substrate; the bench injects canned frames.

> Format per community reverse engineering — validate against real sensors.
"""

from __future__ import annotations

import struct

from openvan_core.ble import alias_for
from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport

TPMS_MANUFACTURER_ID = 0x0100


def parse_tpms(payload: bytes) -> dict[str, float] | None:
    if len(payload) != 16:
        return None
    pressure_raw, temp_raw, battery, alarm = struct.unpack("<iib?", payload[6:16])
    return {
        "pressure_bar": round(pressure_raw / 100000.0, 3),
        "temperature": round(temp_raw / 100.0, 1),
        "battery_pct": float(battery),
        "alarm": float(bool(alarm)),
    }


class Tpms(Integration):
    info = IntegrationInfo(
        id="tpms",
        name="BLE TPMS (valve-cap)",
        category="vehicle",
        vendor="Generic / TPMSII",
        transports=[Transport.BLE],
        local=True,
        offline_capable=True,
        discovery="ble_scan",
        permissions=Permissions(read=True, control=False, configure=True),
        safety_class=0,
        status=Status.COMMUNITY,
        priority="P2",
        provides=["tpms.<sensor>.pressure_bar", "tpms.<sensor>.temperature",
                  "tpms.<sensor>.battery_pct", "tpms.<sensor>.alarm"],
        description=(
            "Universal BLE valve-cap tire sensors — pressure, temperature and "
            "sensor battery for every wheel (trailers and duals included)."
        ),
        config_fields=[
            {"key": "aliases", "label": "Devices", "type": "list", "default": [],
             "item_fields": [
                 {"key": "id", "label": "MAC / id", "type": "text"},
                 {"key": "alias", "label": "Wheel (e.g. front_left)", "type": "text"},
             ]},
        ],
        warning="Advertisement format per community reverse engineering — validate against real sensors.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._unsub = None

    async def async_setup(self) -> None:
        await super().async_setup()
        if self.ble is not None:
            self._unsub = self.ble.subscribe(self._on_adv, manufacturer_id=TPMS_MANUFACTURER_ID)
            self.live = getattr(self.ble, "plan", None) == "bleak"

    async def async_teardown(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        await super().async_teardown()

    async def _on_adv(self, adv) -> None:
        data = parse_tpms(adv.manufacturer_data.get(TPMS_MANUFACTURER_ID, b""))
        if data is None:
            return
        fallback = adv.address.replace(":", "").lower()[-4:] or "tire"
        sensor = alias_for(self.config.get("aliases"), adv.address, fallback)
        for measure, value in data.items():
            await self.twin.set_signal(f"tpms.{sensor}.{measure}", value, source=self.info.id)

    async def simulate(self, dt: float) -> None:
        # Four healthy demo tires, front pair slightly warmer while driving.
        moving = False
        try:
            moving = float(self.twin.get("vehicle.speed_kmh")) > 0
        except (TypeError, ValueError):
            pass
        for tire, base in (("fl", 2.6), ("fr", 2.6), ("rl", 2.8), ("rr", 2.8)):
            await self.twin.set_signal(f"tpms.{tire}.pressure_bar", base, source="tpms")
            await self.twin.set_signal(f"tpms.{tire}.temperature", 28.0 if moving else 15.0, source="tpms")
