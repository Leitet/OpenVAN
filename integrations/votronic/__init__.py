"""Votronic — battery computers, solar regulators and chargers (Display Link).

Votronic gear is everywhere in DE/Nordic vans. Its **Display Link** port
continuously broadcasts 16-byte frames (passive bus — we only listen):

    [0xAA sync] [type] [13 data bytes] [XOR checksum over type+data]

Frame types and layouts per syssi/esphome-votronic (Apache-2.0 — layout facts
used with attribution; implementation original):

* ``0x1A`` solar regulator — battery V, PV V/I, controller temp, status bits
* ``0x3A`` mains charger  — battery I/II V, charge current, load %, temp
* ``0x7A`` charging converter (booster) — same layout as the charger
* ``0xCA``/``0xDA`` battery computer (Smart Shunt) — voltages, remaining
  capacity, SoC, current, nominal capacity

The wire is reached through the pluggable link layer (``link: tcp`` for an
EW11-class bridge — set it to Votronic's unusual **1000 baud** — or ``serial``
for a USB-UART adapter). Readings normalise to ``votronic.*`` auto-entities;
while live, the battery computer mirrors into ``house_battery.*`` and the solar
regulator into ``solar.power`` so every advisor/prediction runs on real data.

> Frame layouts per the syssi component — **unvalidated against real Votronic
> hardware here** (hardware-validation backlog).
"""

from __future__ import annotations

import asyncio
from typing import Any

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport
from openvan_core.transports.links import create_link

FRAME_START = 0xAA
FRAME_LEN = 16
VOTRONIC_BAUD = 1000  # the Display Link's fixed, unusual rate

TYPE_SOLAR = 0x1A
TYPE_CHARGER = 0x3A
TYPE_CONVERTER = 0x7A
TYPE_BATTERY_INFO1 = 0xCA
TYPE_BATTERY_INFO2 = 0xDA
TYPE_BATTERY_INFO3 = 0xFA


def checksum(frame: bytes) -> int:
    """XOR over everything between the sync byte and the checksum itself."""
    value = 0
    for byte in frame[1:FRAME_LEN - 1]:
        value ^= byte
    return value


def _crc_ok(frame: bytes) -> bool:
    return len(frame) == FRAME_LEN and checksum(frame) == frame[FRAME_LEN - 1]


def extract_frames(buffer: bytearray) -> list[bytes]:
    """Pop every complete, checksum-valid frame from ``buffer`` (mutating it),
    resyncing past garbage on the passive bus."""
    frames: list[bytes] = []
    i = 0
    while i + FRAME_LEN <= len(buffer):
        if buffer[i] != FRAME_START:
            i += 1
            continue
        candidate = bytes(buffer[i:i + FRAME_LEN])
        if _crc_ok(candidate):
            frames.append(candidate)
            del buffer[:i + FRAME_LEN]
            i = 0
        else:
            i += 1
    if i:
        del buffer[:i]
    return frames


def _u16(frame: bytes, i: int) -> int:
    return frame[i] | (frame[i + 1] << 8)


def _s16(frame: bytes, i: int) -> int:
    value = _u16(frame, i)
    return value - 0x10000 if value & 0x8000 else value


def parse_frame(frame: bytes) -> tuple[str, dict[str, Any]] | None:
    """One validated frame → (group, measures). Unknown types → None."""
    kind = frame[1]
    if kind == TYPE_SOLAR:
        pv_voltage = _u16(frame, 4) * 0.01
        pv_current = _u16(frame, 6) * 0.1
        return "solar", {
            "battery_voltage": round(_u16(frame, 2) * 0.01, 2),
            "pv_voltage": round(pv_voltage, 2),
            "pv_current": round(pv_current, 1),
            "pv_power": round(pv_voltage * pv_current, 1),
            "controller_temperature": float(frame[11]),
            "active": bool(frame[14] & (1 << 3)),
            "reduced": bool(frame[14] & (1 << 4)),
            "aes_active": bool(frame[14] & (1 << 5)),
        }
    if kind in (TYPE_CHARGER, TYPE_CONVERTER):
        group = "charger" if kind == TYPE_CHARGER else "converter"
        battery_voltage = _u16(frame, 2) * 0.01
        current = _s16(frame, 6) * 0.1
        return group, {
            "battery_voltage": round(battery_voltage, 2),
            "battery2_voltage": round(_u16(frame, 4) * 0.01, 2),
            "current": round(current, 1),
            "power": round(current * battery_voltage, 1),
            "load_pct": float(frame[10]),
            "controller_temperature": round(frame[11] * 0.1, 1),
            "active": bool(frame[14] & (1 << 3)),
        }
    if kind == TYPE_BATTERY_INFO1:
        battery_voltage = _u16(frame, 2) * 0.01
        current = _s16(frame, 12) * 0.001
        return "battery", {
            "voltage": round(battery_voltage, 2),
            "battery2_voltage": round(_u16(frame, 4) * 0.01, 2),
            "capacity_remaining_ah": float(_u16(frame, 6)),
            "soc": float(frame[10]),
            "current": round(current, 3),
            "power": round(current * battery_voltage, 1),
        }
    if kind == TYPE_BATTERY_INFO2:
        return "battery", {
            "nominal_capacity_ah": round(_u16(frame, 6) * 0.1, 1),
        }
    return None


class Votronic(Integration):
    info = IntegrationInfo(
        id="votronic",
        name="Votronic (Display Link)",
        category="energy",
        vendor="Votronic",
        transports=[Transport.SERIAL],
        local=True,
        offline_capable=True,
        discovery="manual",
        permissions=Permissions(read=True, control=False, configure=True),
        safety_class=0,
        status=Status.REVERSE_ENGINEERED,
        priority="P0",
        provides=[
            "votronic.battery.soc", "votronic.battery.current",
            "votronic.solar.pv_power", "votronic.charger.current",
            "house_battery.soc (mirrored)", "solar.power (mirrored)",
        ],
        description=(
            "Votronic battery computers (Smart Shunt), solar regulators and "
            "chargers via the passive Display Link bus — an EW11-class bridge at "
            "1000 baud (no extras) or a USB adapter. Live readings feed the "
            "house-battery advisors and solar forecasting."
        ),
        config_fields=[
            {"key": "mode", "label": "Connection", "type": "select",
             "options": ["sim", "link"], "default": "sim"},
            {"key": "link", "label": "Link", "type": "select",
             "options": ["tcp", "serial"], "default": "tcp"},
            {"key": "host", "label": "Bridge host (tcp link)", "type": "text"},
            {"key": "port", "label": "Bridge port", "type": "text", "default": "8899"},
            {"key": "device", "label": "Serial device (serial link)", "type": "text"},
            {"key": "baud", "label": "Baud", "type": "text", "default": "1000"},
            {"key": "feeds_house_battery", "label": "Feed house battery signals",
             "type": "select", "options": ["yes", "no"], "default": "yes"},
        ],
        warning=(
            "Frame layouts per the syssi/esphome-votronic component (Apache-2.0) — "
            "validate against real Votronic hardware."
        ),
    )

    def transport_mode(self) -> str:
        return str(self.config.get("mode", "sim") or "sim")

    def _make_link(self):
        cfg = dict(self.config)
        cfg.setdefault("baud", VOTRONIC_BAUD)
        return create_link(cfg)

    def _feeds_house_battery(self) -> bool:
        return str(self.config.get("feeds_house_battery", "yes")) != "no"

    async def _apply(self, frame: bytes) -> None:
        parsed = parse_frame(frame)
        if parsed is None:
            return
        group, measures = parsed
        for measure, value in measures.items():
            await self.twin.set_signal(
                f"votronic.{group}.{measure}", value, source=self.info.id
            )
        # Mirrors: the world's signals, provided by real hardware while live.
        if group == "battery" and self._feeds_house_battery():
            mirror = {"soc": "house_battery.soc", "voltage": "house_battery.voltage",
                      "current": "house_battery.current"}
            for measure, signal in mirror.items():
                if measure in measures:
                    await self.twin.set_signal(signal, measures[measure], source=self.info.id)
        if group == "solar" and "pv_power" in measures:
            await self.twin.set_signal("solar.power", measures["pv_power"], source=self.info.id)

    async def run_transport(self) -> None:
        if self.transport_mode() != "link":
            raise NotImplementedError
        if not (self.config.get("host") or self.config.get("device")):
            raise NotImplementedError
        link = self._make_link()
        await link.open()
        buffer = bytearray()
        self.live = True
        await self.bus.publish("integration.changed", {"id": self.info.id, "live": True})
        try:
            while True:
                chunk = await link.read(64, timeout=1.0)
                if chunk:
                    buffer += chunk
                    for frame in extract_frames(buffer):
                        await self._apply(frame)
                else:
                    await asyncio.sleep(0.05)  # passive bus — quiet is normal
        finally:
            await link.close()

    async def simulate(self, dt: float) -> None:
        def _f(key: str, default: float) -> float:
            try:
                return float(self.twin.get(key))
            except (TypeError, ValueError):
                return default

        await self.twin.set_signal(
            "votronic.battery.soc", _f("house_battery.soc", 82.0), source=self.info.id
        )
        await self.twin.set_signal(
            "votronic.battery.voltage", _f("house_battery.voltage", 12.9), source=self.info.id
        )
        await self.twin.set_signal(
            "votronic.solar.pv_power", _f("solar.power", 240.0), source=self.info.id
        )
