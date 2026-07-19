"""Victron Venus OS / GX — the flagship energy integration.

A Cerbo GX (or any Venus OS device) exposes the whole energy system over local
**MQTT** and **Modbus-TCP**; individual products also speak **VE.Direct** over USB.
This is the single highest-value integration — one connection covers the battery
monitor, MPPT solar, DC-DC/alternator, shore charger and inverter.

Three modes, chosen in Settings → Integrations:

* ``sim`` (default) — the driver *simulates* the normalised energy signals a GX
  would publish (offline, no hardware). What the bench/product UI exercise today.
* ``modbus_tcp`` — poll a real GX's holding registers (the CCGX Modbus-TCP map).
* ``mqtt`` — subscribe to a real Venus OS broker's ``N/<portal>/…`` topics.

Both real paths normalise into the **same twin signals** the plugins already
consume, and both fall back to ``simulate()`` whenever the device is unreachable
(offline-first, Rule 3). The transport clients are pure-stdlib
(:mod:`openvan_core.transports`) — no vendor SDK.

> The register addresses / scale factors below follow Victron's published CCGX
> Modbus-TCP register list for the *system* service. Confirm them against your
> device's firmware before trusting the numbers on a real van (simulators are not
> reality — measure before shipping).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport
from openvan_core.transports import AsyncModbusTcpClient, AsyncMqttClient
from openvan_core.transports.modbus_tcp import to_int16


# --- Modbus-TCP register map (com.victronenergy.system, default unit id 100) ---
# One contiguous block read covers battery (840..843) and DC-coupled PV (850).
_BLOCK_START = 840
_BLOCK_COUNT = 11  # 840..850 inclusive


@dataclass(frozen=True)
class _Reg:
    offset: int  # index within the block (address - _BLOCK_START)
    signal: str
    scale: float
    signed: bool


_REGISTERS = (
    _Reg(0, "house_battery.voltage", 100.0, False),  # 840, V ×100
    _Reg(1, "house_battery.current", 10.0, True),    # 841, A ×10
    _Reg(3, "house_battery.soc", 1.0, False),        # 843, %
    _Reg(10, "solar.power", 1.0, True),              # 850, W (DC-coupled PV)
)


def normalise_registers(block: list[int]) -> dict[str, float]:
    """Map a raw 840-block register read into normalised twin signals."""
    out: dict[str, float] = {}
    for r in _REGISTERS:
        if r.offset >= len(block):
            continue
        word = to_int16(block[r.offset]) if r.signed else block[r.offset]
        out[r.signal] = round(word / r.scale, 3)
    return out


# --- MQTT topic map (Venus OS system service) --------------------------------
# Topic suffix (after N/<portal>/) → normalised signal.
_TOPIC_SUFFIX = {
    "system/0/Dc/Battery/Voltage": "house_battery.voltage",
    "system/0/Dc/Battery/Current": "house_battery.current",
    "system/0/Dc/Battery/Soc": "house_battery.soc",
    "system/0/Dc/Pv/Power": "solar.power",
}


def normalise_topic(topic: str, payload: bytes) -> tuple[str, float] | None:
    """Map a Venus MQTT ``N/<portal>/…`` message to a normalised signal, or None.

    Venus payloads are JSON ``{"value": <number|null>}``; a null value (device
    absent) is ignored so we never write a bogus reading.
    """
    for suffix, signal in _TOPIC_SUFFIX.items():
        if topic.endswith(suffix):
            try:
                value = json.loads(payload.decode("utf-8")).get("value")
            except (ValueError, AttributeError):
                return None
            if value is None:
                return None
            try:
                return signal, round(float(value), 3)
            except (TypeError, ValueError):
                return None
    return None


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
            "house_battery.voltage", "house_battery.current", "house_battery.soc",
            "solar.power", "solar.yield_today_wh", "alternator.power",
            "shore.connected", "inverter.on", "inverter.temperature",
        ],
        description=(
            "Cerbo GX / Venus OS over local MQTT + Modbus-TCP. Covers battery, "
            "MPPT solar, DC-DC, shore charger and inverter in one connection."
        ),
        config_fields=[
            {"key": "mode", "label": "Connection", "type": "select",
             "options": ["sim", "modbus_tcp", "mqtt"], "default": "sim"},
            {"key": "host", "label": "GX host / IP", "type": "text"},
            {"key": "port", "label": "Port", "type": "text"},
            {"key": "unit_id", "label": "Modbus unit ID", "type": "text", "default": "100"},
            {"key": "portal_id", "label": "MQTT portal ID (VRM)", "type": "text"},
        ],
        warning="Confirm Modbus register addresses against your GX firmware before relying on values.",
    )

    # Poll cadence for the Modbus path (seconds).
    POLL_INTERVAL = 2.0

    async def run_transport(self) -> None:
        mode = self.transport_mode()
        if mode == "modbus_tcp":
            await self._run_modbus()
        elif mode == "mqtt":
            await self._run_mqtt()
        else:
            raise NotImplementedError

    async def _run_modbus(self) -> None:
        host = self.config.get("host")
        if not host:
            raise NotImplementedError  # nothing to connect to → stay simulated
        port = int(self.config.get("port") or 502)
        unit = int(self.config.get("unit_id") or 100)
        client = AsyncModbusTcpClient(host, port, unit_id=unit)
        await client.connect()
        self.live = True
        await self.bus.publish("integration.changed", {"id": self.info.id, "live": True})
        try:
            while True:
                block = await client.read_holding_registers(_BLOCK_START, _BLOCK_COUNT)
                for signal, value in normalise_registers(block).items():
                    await self.twin.set_signal(signal, value, source=self.info.id)
                await asyncio.sleep(self.POLL_INTERVAL)
        finally:
            await client.close()

    async def _run_mqtt(self) -> None:
        host = self.config.get("host")
        if not host:
            raise NotImplementedError
        port = int(self.config.get("port") or 1883)
        client = AsyncMqttClient(
            host, port, client_id="openvan-victron",
            username=self.config.get("username") or None,
            password=self.config.get("password") or None,
        )
        await client.connect()
        await client.subscribe("N/#")
        # Venus only publishes once it sees a keepalive on the portal's request topic.
        portal = self.config.get("portal_id")
        if portal:
            await client.publish(f"R/{portal}/keepalive", b"")
        self.live = True
        await self.bus.publish("integration.changed", {"id": self.info.id, "live": True})
        try:
            async for topic, payload in client.messages():
                hit = normalise_topic(topic, payload)
                if hit is not None:
                    await self.twin.set_signal(hit[0], hit[1], source=self.info.id)
        finally:
            await client.close()

    # No simulate(): the van's energy state (solar yield, alternator, inverter temp)
    # is environment physics driven by the simulation layer, not invented here — a
    # Victron in sim mode is a reader with nothing to fabricate. On real hardware,
    # run_transport() streams the GX's own readings over the wire.
