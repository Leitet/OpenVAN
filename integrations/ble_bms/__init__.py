"""BLE BMS — battery management systems over GATT (JBD/Overkill first).

The heart of nearly every DIY LiFePO4 van build is a BLE-capable BMS. This driver
speaks the **JBD** protocol (a.k.a. Overkill Solar; also sold as Xiaoxiang) —
UART-over-GATT with notify ``ff01`` / write ``ff02`` — and is structured so more
protocols (JK, Daly, Seplos) can join behind the same driver, per the market
research's "one multi-vendor driver, not per-brand" call.

Like Mopeka, it feeds the **core house-battery signals** (SoC/voltage/current) so
every existing advisor, prediction and safety rule runs on a non-Victron battery
unchanged — that's the point.

Built on the BLE substrate's GATT sessions: in sim the bench/tests register a
programmable :class:`SimBleDevice`; with the ``ble`` extra the same code talks to
a real pack.

> Protocol per the widely published JBD/Overkill documentation and community
> implementations — **unvalidated against a real BMS here** (flagged in the
> hardware-validation backlog).
"""

from __future__ import annotations

import asyncio
import struct

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport

NOTIFY_CHAR = "ff01"
WRITE_CHAR = "ff02"
CMD_BASIC_INFO = 0x03


def checksum(data: bytes) -> int:
    """JBD checksum: 0x10000 minus the byte sum (mod 0x10000)."""
    return (0x10000 - sum(data)) & 0xFFFF


def build_request(cmd: int) -> bytes:
    body = bytes([cmd, 0x00])
    return b"\xdd\xa5" + body + struct.pack(">H", checksum(body)) + b"\x77"


def parse_frame(frame: bytes) -> tuple[int, bytes] | None:
    """Validate a full response frame → (command, payload), else None."""
    if len(frame) < 7 or frame[0] != 0xDD or frame[-1] != 0x77:
        return None
    cmd, status, length = frame[1], frame[2], frame[3]
    if status != 0x00 or len(frame) != 4 + length + 3:
        return None
    payload = frame[4 : 4 + length]
    (chk,) = struct.unpack(">H", frame[-3:-1])
    if checksum(frame[2 : 4 + length]) != chk:
        return None
    return cmd, payload


def parse_basic_info(payload: bytes) -> dict[str, float] | None:
    """JBD basic-info (0x03): pack voltage/current/capacity/SoC/temps."""
    if len(payload) < 23:
        return None
    voltage, current, remaining, nominal, cycles = struct.unpack(">HhHHH", payload[0:10])
    soc = payload[19]
    fets = payload[20]
    ntc_count = payload[22]
    out: dict[str, float] = {
        "voltage": round(voltage * 0.01, 2),
        "current": round(current * 0.01, 2),
        "remaining_ah": round(remaining * 0.01, 2),
        "nominal_ah": round(nominal * 0.01, 2),
        "cycles": float(cycles),
        "soc": float(soc),
        "charging_enabled": float(bool(fets & 0x01)),
        "discharging_enabled": float(bool(fets & 0x02)),
    }
    temps = []
    for i in range(ntc_count):
        off = 23 + i * 2
        if off + 2 <= len(payload):
            (raw,) = struct.unpack(">H", payload[off : off + 2])
            temps.append(raw * 0.1 - 273.1)
    if temps:
        out["temperature"] = round(max(temps), 1)
    return out


class FrameBuffer:
    """Reassembles frames split across BLE notifications."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> list[bytes]:
        self._buf += chunk
        frames: list[bytes] = []
        while True:
            if len(self._buf) < 4:
                return frames
            if self._buf[0] != 0xDD:  # resync to a start byte
                self._buf = self._buf[1:]
                continue
            total = 4 + self._buf[3] + 3
            if len(self._buf) < total:
                return frames
            frames.append(bytes(self._buf[:total]))
            self._buf = self._buf[total:]


class BleBms(Integration):
    info = IntegrationInfo(
        id="ble_bms",
        name="BLE BMS (JBD / Overkill Solar)",
        category="energy",
        vendor="JBD / multi-vendor",
        transports=[Transport.BLE],
        local=True,
        offline_capable=True,
        discovery="ble_scan",
        permissions=Permissions(read=True, control=False, configure=True),
        safety_class=0,  # read-only; FET control would be class 3+ (later, via safety)
        status=Status.COMMUNITY,
        priority="P0",
        provides=["blebms.<id>.soc", "blebms.<id>.voltage", "blebms.<id>.current",
                  "house_battery.* (mirrored)"],
        description=(
            "DIY LiFePO4 battery monitoring over BLE (JBD/Overkill/Xiaoxiang; more "
            "protocols to follow). Feeds the house-battery signals so every advisor "
            "and safety rule works on a non-Victron pack."
        ),
        config_fields=[
            {"key": "mode", "label": "Connection", "type": "select",
             "options": ["sim", "ble"], "default": "sim"},
            {"key": "address", "label": "BMS MAC address", "type": "text"},
            {"key": "protocol", "label": "Protocol", "type": "select",
             "options": ["jbd"], "default": "jbd"},
            {"key": "feeds_house_battery", "label": "Feeds house battery", "type": "select",
             "options": ["yes", "no"], "default": "yes"},
            {"key": "poll_s", "label": "Poll interval (s)", "type": "text", "default": "5"},
        ],
        warning="JBD protocol per community documentation — validate against a real BMS.",
    )

    def transport_mode(self) -> str:
        # "ble" is this driver's live mode (the base treats anything != sim as live).
        return str(self.config.get("mode", "sim") or "sim")

    async def run_transport(self) -> None:
        if self.transport_mode() != "ble":
            raise NotImplementedError
        address = self.config.get("address")
        if not address or self.ble is None:
            raise NotImplementedError  # nothing to connect to → stay simulated
        try:
            poll_s = float(self.config.get("poll_s") or 5.0)
        except (TypeError, ValueError):
            poll_s = 5.0
        device = await self.ble.connect(address)
        buffer = FrameBuffer()
        device_id = address.replace(":", "").lower()[-4:] or "pack"

        async def _on_notify(data: bytes) -> None:
            for frame in buffer.feed(data):
                parsed = parse_frame(frame)
                if parsed is None:
                    continue
                cmd, payload = parsed
                if cmd == CMD_BASIC_INFO:
                    info = parse_basic_info(payload)
                    if info:
                        await self._publish(device_id, info)

        try:
            await device.start_notify(NOTIFY_CHAR, _on_notify)
            self.live = True
            await self.bus.publish("integration.changed", {"id": self.info.id, "live": True})
            while True:
                await device.write(WRITE_CHAR, build_request(CMD_BASIC_INFO))
                await asyncio.sleep(poll_s)
        finally:
            await device.disconnect()

    async def _publish(self, device_id: str, info: dict[str, float]) -> None:
        for measure, value in info.items():
            await self.twin.set_signal(f"blebms.{device_id}.{measure}", value, source=self.info.id)
        # The layering payoff: a non-Victron pack drives every battery advisor,
        # prediction and load-shedding rule through the core signals.
        if str(self.config.get("feeds_house_battery") or "yes") == "yes":
            await self.twin.set_signal("house_battery.soc", info["soc"], source=self.info.id)
            await self.twin.set_signal("house_battery.voltage", info["voltage"], source=self.info.id)
            await self.twin.set_signal("house_battery.current", info["current"], source=self.info.id)

    async def simulate(self, dt: float) -> None:
        # Demo pack mirroring the seeded house battery (reverse of the live flow).
        def _f(key, default):
            try:
                return float(self.twin.get(key))
            except (TypeError, ValueError):
                return default

        await self.twin.set_signal("blebms.demo.soc", _f("house_battery.soc", 82.0), source="ble_bms")
        await self.twin.set_signal("blebms.demo.voltage", _f("house_battery.voltage", 12.9), source="ble_bms")
        await self.twin.set_signal("blebms.demo.current", _f("house_battery.current", -4.2), source="ble_bms")
