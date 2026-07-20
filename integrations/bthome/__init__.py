"""BTHome — the open BLE sensor standard (Shelly BLU, Xiaomi-ATC, b-parasite, …).

BTHome is the converging open format for cheap BLE sensors: a broadcast-only
service-data payload (UUID ``fcd2``) carrying typed measurements. One driver
covers every compliant thermometer/hygrometer — the market research's answer to
"fridge temp + pet heat-safety with €10 sensors".

Built on the shared BLE substrate: this driver never touches a radio — it
subscribes to Core's scanner with a service-UUID filter. On the sim radio the
bench injects canned frames (Rule 1); with the ``ble`` extra installed the same
parser sees real air. v2 unencrypted payloads only (encrypted BTHome needs the
per-device key — backlog).
"""

from __future__ import annotations

import re
import struct

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport

BTHOME_UUID = "fcd2"

# BTHome v2 object id → (name, byte length, decoder). Unknown ids stop the parse
# (lengths vary per id, so we can't skip what we don't know — fail safe).
_OBJECTS = {
    0x00: ("packet_id", 1, lambda b: b[0]),
    0x01: ("battery_pct", 1, lambda b: b[0]),
    0x02: ("temperature", 2, lambda b: struct.unpack("<h", b)[0] * 0.01),
    0x03: ("humidity", 2, lambda b: struct.unpack("<H", b)[0] * 0.01),
    0x0C: ("voltage", 2, lambda b: struct.unpack("<H", b)[0] * 0.001),
}


def parse_bthome(payload: bytes) -> dict[str, float] | None:
    """Decode a BTHome v2 service-data payload → measurements, or None if not v2
    unencrypted. Stops cleanly at the first unknown object id."""
    if not payload:
        return None
    info = payload[0]
    if info & 0x01:  # encrypted — needs the bind key; not supported yet
        return None
    if (info >> 5) & 0x07 != 2:  # BTHome version 2 only
        return None
    out: dict[str, float] = {}
    i = 1
    while i < len(payload):
        obj = payload[i]
        spec = _OBJECTS.get(obj)
        if spec is None:
            break
        name, length, decode = spec
        chunk = payload[i + 1 : i + 1 + length]
        if len(chunk) < length:
            break
        if name != "packet_id":
            out[name] = round(float(decode(chunk)), 3)
        i += 1 + length
    return out or None


def device_id(address: str, name: str) -> str:
    if name:
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        if slug:
            return slug
    return address.replace(":", "").lower()[-4:] or "unknown"


class BtHome(Integration):
    info = IntegrationInfo(
        id="bthome",
        name="BTHome sensors",
        category="sensors",
        vendor="BTHome / open standard",
        transports=[Transport.BLE],
        local=True,
        offline_capable=True,
        discovery="ble_scan",
        permissions=Permissions(read=True, control=False, configure=False),
        safety_class=0,
        status=Status.OPEN,
        priority="P1",
        provides=["bthome.<device>.temperature", "bthome.<device>.humidity",
                  "bthome.<device>.battery_pct", "bthome.<device>.voltage"],
        description=(
            "Any BTHome v2 broadcaster (Shelly BLU, Xiaomi ATC firmware, "
            "b-parasite, …) — cheap wireless temp/humidity for fridge and "
            "pet-safety monitoring. One driver for the whole standard."
        ),
        warning="Encrypted BTHome devices are not supported yet (needs bind keys).",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._unsub = None

    async def async_setup(self) -> None:
        await super().async_setup()
        if self.ble is not None:
            self._unsub = self.ble.subscribe(self._on_adv, service_uuid=BTHOME_UUID)
            # Real radio → real air; the sim radio carries bench injections.
            self.live = getattr(self.ble, "plan", None) == "bleak"

    async def async_teardown(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        await super().async_teardown()

    async def _on_adv(self, adv) -> None:
        data = parse_bthome(adv.service_data.get(BTHOME_UUID, b""))
        if not data:
            return
        device = device_id(adv.address, adv.name)
        for measure, value in data.items():
            await self.twin.set_signal(f"bthome.{device}.{measure}", value, source=self.info.id)

    async def simulate(self, dt: float) -> None:
        # A canned fridge thermometer so the catalog demo works with zero setup;
        # tracks a bit above the twin's fridge temperature.
        try:
            fridge = float(self.twin.get("fridge.temp_c"))
        except (TypeError, ValueError):
            fridge = 4.0
        # "demo_" prefix so the canned device never collides with a real/injected one.
        await self.twin.set_signal("bthome.demo_probe.temperature", round(fridge + 0.3, 2), source="bthome")
        await self.twin.set_signal("bthome.demo_probe.battery_pct", 91, source="bthome")
