"""The pluggable link layer (many ways to reach a wire) + Modbus RTU over it,
and the EPEver driver end-to-end against a scripted device."""

from __future__ import annotations

import asyncio
import struct

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.transports.links import (
    LINK_TYPES,
    SimSerialLink,
    TcpSerialLink,
    create_link,
)
from openvan_core.transports.modbus_rtu import (
    AsyncModbusRtuClient,
    ModbusRtuError,
    build_read_request,
    crc16,
    parse_read_response,
)


# --- links -------------------------------------------------------------------

def test_link_factory_options():
    assert isinstance(create_link({"link": "sim"}), SimSerialLink)
    tcp = create_link({"link": "tcp", "host": "10.0.0.5"})
    assert isinstance(tcp, TcpSerialLink) and tcp.port == 8899  # EW11 default
    with pytest.raises(ValueError):
        create_link({"link": "tcp"})  # no host
    with pytest.raises(ValueError):
        create_link({"link": "carrier-pigeon"})
    assert set(LINK_TYPES) >= {"sim", "tcp", "serial"}


async def test_sim_link_scripted_responder():
    link = SimSerialLink(responder=lambda req: b"pong" if req == b"ping" else None)
    await link.open()
    await link.write(b"ping")
    assert await link.read() == b"pong"
    assert link.writes == [b"ping"]
    assert await link.read(timeout=0.05) == b""  # empty on timeout


async def test_tcp_link_against_loopback():
    async def handle(reader, writer):
        try:
            data = await reader.read(64)
            writer.write(b"echo:" + data)
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        link = TcpSerialLink("127.0.0.1", port)
        await link.open()
        await link.write(b"hello")
        assert await link.read() == b"echo:hello"
        await link.close()
    finally:
        server.close()


# --- Modbus RTU codec --------------------------------------------------------

def test_crc16_known_vector():
    # The canonical example: 01 03 00 00 00 0A → CRC C5 CD (lo byte first on the wire).
    frame = build_read_request(1, 0x03, 0x0000, 10)
    assert frame == bytes.fromhex("01030000000ac5cd")


def test_rtu_response_parse_and_rejects():
    payload = struct.pack(">HH", 1234, 82)
    body = bytes([1, 0x04, 4]) + payload
    frame = body + struct.pack("<H", crc16(body))
    assert parse_read_response(frame, 1, 0x04, 2) == [1234, 82]
    # CRC flip → rejected.
    bad = bytearray(frame)
    bad[3] ^= 0xFF
    with pytest.raises(ModbusRtuError):
        parse_read_response(bytes(bad), 1, 0x04, 2)
    # Exception response.
    ebody = bytes([1, 0x84, 0x02])
    with pytest.raises(ModbusRtuError, match="exception"):
        parse_read_response(ebody + struct.pack("<H", crc16(ebody)), 1, 0x04, 2)


async def test_rtu_client_over_sim_link():
    def responder(req: bytes) -> bytes | None:
        # A fake device: any input-register read gets sequential values.
        unit, func, addr, count = struct.unpack(">BBHH", req[:6])
        payload = b"".join(struct.pack(">H", addr % 100 + i) for i in range(count))
        body = bytes([unit, func, count * 2]) + payload
        return body + struct.pack("<H", crc16(body))

    client = AsyncModbusRtuClient(SimSerialLink(responder=responder), unit_id=1, timeout=0.5)
    await client.open()
    regs = await client.read_input_registers(0x3100, 4)
    assert regs == [0x3100 % 100, 0x3100 % 100 + 1, 0x3100 % 100 + 2, 0x3100 % 100 + 3]


# --- EPEver end-to-end -------------------------------------------------------

def _epever_responder(req: bytes) -> bytes | None:
    unit, func, addr, count = struct.unpack(">BBHH", req[:6])
    if addr == 0x3100:  # main block: PV 18.5V / 3.24A / 60W, batt 13.42V / 4.4A
        regs = [1850, 324, 6000, 0, 1342, 440, 5900, 0, 0, 0, 0, 0, 0, 0, 1200, 0]
    elif addr == 0x3110:  # temps + SoC 76%
        regs = [2510, 3105, 0, 0, 0, 0, 0, 0, 0, 0, 76]
    else:
        return None
    payload = b"".join(struct.pack(">H", r) for r in regs[:count])
    body = bytes([unit, func, count * 2]) + payload
    return body + struct.pack("<H", crc16(body))


def test_epever_parsers(tmp_path):
    # Parsers are importable once the driver is discovered; craft directly.
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "integrations"))
    from epever import parse_main, parse_temps

    main = parse_main([1850, 324, 6000, 0, 1342, 440, 5900, 0, 0, 0, 0, 0, 0, 0, 1200, 0])
    assert main["pv_voltage"] == 18.5 and main["pv_power"] == 60.0
    assert main["battery_voltage"] == 13.42 and main["load_power"] == 12.0
    temps = parse_temps([2510, 3105, 0, 0, 0, 0, 0, 0, 0, 0, 76])
    assert temps["battery_temp"] == 25.1 and temps["soc"] == 76.0


async def test_epever_live_over_sim_link(tmp_path):
    core = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, simulate=False, data_dir=tmp_path)
    )
    await core.start()
    try:
        inst = core.integrations.get("epever")
        inst._make_link = lambda: SimSerialLink(responder=_epever_responder)
        await core.set_integration_enabled("epever", True)
        await core.set_integration_config(
            "epever", {"mode": "rtu", "host": "x", "poll_s": "0.05"}
        )
        for _ in range(60):
            if core.twin.get("epever.u1.soc") == 76.0:
                break
            await asyncio.sleep(0.05)
        assert core.twin.get("epever.u1.pv_power") == 60.0
        assert core.twin.get("epever.u1.soc") == 76.0
        # Live PV drives the world's solar signal → forecasting/advisors.
        assert core.twin.get("solar.power") == 60.0
        assert inst.live is True
    finally:
        await core.stop()
