"""EPEver / EPsolar Tracer MPPT — the budget solar controller of choice.

Speaks Modbus RTU over RS-485. Thanks to the pluggable link layer this works
several ways — pick one in the config, like choosing a driver:

* ``link: tcp`` — an RS-485↔WiFi bridge (Elfin EW11 & friends, the smart-van
  community's standard wiring; default port 8899). Pure stdlib, works today.
* ``link: serial`` — a USB-RS485 stick (needs the optional ``serial`` extra).
* ``mode: sim`` — the catalog demo against the twin (Rule 1).

Registers per EPEver's published Modbus map (input registers 0x3100 block:
PV volts/amps/power, battery volts/charge current; 0x3110 block: temperatures
and SoC). Live values mirror into ``solar.power`` so the existing solar
forecasting/advisors run on real hardware.

> Register map per the published EPEver PDF — **unvalidated on a real Tracer
> here** (hardware-validation backlog).
"""

from __future__ import annotations

import asyncio

from openvan_core import Integration, IntegrationInfo, Permissions, Status, Transport
from openvan_core.transports.links import create_link
from openvan_core.transports.modbus_rtu import AsyncModbusRtuClient

BLOCK_MAIN = 0x3100  # 16 regs: PV + battery live values
BLOCK_TEMPS = 0x3110  # 11 regs: temps … SoC at 0x311A


def parse_main(regs: list[int]) -> dict[str, float]:
    """The 0x3100 input-register block (16 regs)."""
    if len(regs) < 16:
        return {}
    return {
        "pv_voltage": round(regs[0] * 0.01, 2),
        "pv_current": round(regs[1] * 0.01, 2),
        "pv_power": round((regs[2] | (regs[3] << 16)) * 0.01, 1),
        "battery_voltage": round(regs[4] * 0.01, 2),
        "charge_current": round(regs[5] * 0.01, 2),
        "charge_power": round((regs[6] | (regs[7] << 16)) * 0.01, 1),
        "load_power": round((regs[14] | (regs[15] << 16)) * 0.01, 1),
    }


def parse_temps(regs: list[int]) -> dict[str, float]:
    """The 0x3110 block (11 regs): battery/device temperature, SoC at +0x0A."""
    if len(regs) < 11:
        return {}
    def _temp(raw: int) -> float:
        return round((raw - 0x10000 if raw & 0x8000 else raw) * 0.01, 1)

    return {
        "battery_temp": _temp(regs[0]),
        "device_temp": _temp(regs[1]),
        "soc": float(regs[10]),
    }


class Epever(Integration):
    info = IntegrationInfo(
        id="epever",
        name="EPEver / EPsolar Tracer",
        category="energy",
        vendor="EPEver",
        transports=[Transport.MODBUS_RTU, Transport.SERIAL],
        local=True,
        offline_capable=True,
        discovery="manual",
        permissions=Permissions(read=True, control=False, configure=True),
        safety_class=0,
        status=Status.OPEN,  # published register map
        priority="P1",
        provides=["epever.<unit>.pv_power", "epever.<unit>.soc", "solar.power (mirrored)"],
        description=(
            "Tracer/XTRA MPPT controllers over Modbus RTU — via an RS-485 WiFi "
            "bridge (EW11-style, no extras needed) or a USB adapter. Live PV data "
            "feeds the solar forecasting."
        ),
        config_fields=[
            {"key": "mode", "label": "Connection", "type": "select",
             "options": ["sim", "rtu"], "default": "sim"},
            {"key": "link", "label": "Link", "type": "select",
             "options": ["tcp", "serial"], "default": "tcp"},
            {"key": "host", "label": "Bridge host (tcp link)", "type": "text"},
            {"key": "port", "label": "Bridge port", "type": "text", "default": "8899"},
            {"key": "device", "label": "Serial device (serial link)", "type": "text"},
            {"key": "baud", "label": "Baud", "type": "text", "default": "115200"},
            {"key": "unit_id", "label": "Modbus unit id", "type": "text", "default": "1"},
            {"key": "poll_s", "label": "Poll interval (s)", "type": "text", "default": "5"},
        ],
        warning="Register map per EPEver's published doc — validate on a real controller.",
    )

    def transport_mode(self) -> str:
        return str(self.config.get("mode", "sim") or "sim")

    def _make_link(self):
        return create_link(self.config)

    async def run_transport(self) -> None:
        if self.transport_mode() != "rtu":
            raise NotImplementedError
        if not (self.config.get("host") or self.config.get("device")):
            raise NotImplementedError  # nowhere to connect → stay simulated
        try:
            unit_id = int(self.config.get("unit_id") or 1)
            poll_s = float(self.config.get("poll_s") or 5.0)
        except (TypeError, ValueError):
            unit_id, poll_s = 1, 5.0
        client = AsyncModbusRtuClient(self._make_link(), unit_id=unit_id)
        await client.open()
        try:
            self.live = True
            await self.bus.publish("integration.changed", {"id": self.info.id, "live": True})
            while True:
                data = parse_main(await client.read_input_registers(BLOCK_MAIN, 16))
                data.update(parse_temps(await client.read_input_registers(BLOCK_TEMPS, 11)))
                for measure, value in data.items():
                    await self.twin.set_signal(f"epever.u{unit_id}.{measure}", value, source=self.info.id)
                # The world's solar signal — live hardware provides it (like a GX would).
                if "pv_power" in data:
                    await self.twin.set_signal("solar.power", data["pv_power"], source=self.info.id)
                await asyncio.sleep(poll_s)
        finally:
            await client.close()

    async def simulate(self, dt: float) -> None:
        def _f(key, default):
            try:
                return float(self.twin.get(key))
            except (TypeError, ValueError):
                return default

        await self.twin.set_signal("epever.demo.pv_power", _f("solar.power", 240.0), source="epever")
        await self.twin.set_signal("epever.demo.battery_voltage", _f("house_battery.voltage", 12.9), source="epever")
