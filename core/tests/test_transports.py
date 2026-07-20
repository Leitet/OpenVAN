"""Pure-stdlib transports: exact codecs + end-to-end against in-process loopback
servers (the 'simulate the external dependency' principle applied to the wire, so
the clients are verifiable offline with no real hardware)."""

from __future__ import annotations

import asyncio
import struct

import pytest

from openvan_core.transports import AsyncModbusTcpClient, AsyncMqttClient, ModbusError
from openvan_core.transports.modbus_tcp import (
    build_read_request,
    parse_read_response,
    to_int16,
    to_int32,
)
from openvan_core.transports.mqtt import (
    build_publish,
    encode_remaining_length,
    read_remaining_length,
)


# --- Modbus codec ------------------------------------------------------------

def test_modbus_request_frame_is_spec_exact():
    # Read holding registers, tid=1, unit=100, addr=840 (0x0348), count=11 (0x000B).
    frame = build_read_request(1, 100, 0x03, 840, 11)
    mbap = struct.pack(">HHHB", 1, 0, 6, 100)  # tid, proto=0, len=6, unit
    pdu = struct.pack(">BHH", 0x03, 840, 11)
    assert frame == mbap + pdu


def test_modbus_parse_response_and_exception():
    body = bytes([0x03, 0x04]) + struct.pack(">HH", 1290, 82)
    assert parse_read_response(body, 0x03, 2) == [1290, 82]
    # Exception response (function | 0x80, code 0x02 illegal address).
    with pytest.raises(ModbusError):
        parse_read_response(bytes([0x83, 0x02]), 0x03, 2)
    # Byte-count mismatch.
    with pytest.raises(ModbusError):
        parse_read_response(bytes([0x03, 0x02, 0x00]), 0x03, 2)


def test_register_sign_helpers():
    assert to_int16(65494) == -42
    assert to_int16(1290) == 1290
    assert to_int32(0xFFFF, 0xFFFF) == -1


# --- Modbus loopback ---------------------------------------------------------

async def _modbus_server(registers: dict[int, int]):
    async def handle(reader, writer):
        try:
            while True:
                header = await reader.readexactly(7)
                tid, _pid, length, unit = struct.unpack(">HHHB", header)
                pdu = await reader.readexactly(length - 1)
                _fc, addr, count = struct.unpack(">BHH", pdu)
                data = b"".join(struct.pack(">H", registers.get(addr + i, 0)) for i in range(count))
                body = bytes([0x03, len(data)]) + data
                writer.write(struct.pack(">HHHB", tid, 0, len(body) + 1, unit) + body)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


async def test_modbus_client_reads_from_loopback():
    server, port = await _modbus_server({840: 1290, 841: 65494, 843: 82, 850: 240})
    async with server:
        client = AsyncModbusTcpClient("127.0.0.1", port, unit_id=100)
        await client.connect()
        block = await client.read_holding_registers(840, 11)
        await client.close()
    assert block[0] == 1290  # voltage ×100
    assert to_int16(block[1]) == -42  # current ×10
    assert block[3] == 82  # SoC
    assert to_int16(block[10]) == 240  # PV W


async def test_modbus_rejects_malformed_length():
    """A garbled MBAP length must raise ModbusError, not readexactly(-1) ValueError."""
    async def handle(reader, writer):
        try:
            await reader.readexactly(12)  # consume the request (MBAP 7 + PDU 5)
            writer.write(struct.pack(">HHHB", 1, 0, 1, 1))  # length=1 → invalid
            await writer.drain()
            await asyncio.sleep(0.2)
        except (asyncio.IncompleteReadError, ConnectionError):
            pass

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        client = AsyncModbusTcpClient("127.0.0.1", port, unit_id=1)
        await client.connect()
        with pytest.raises(ModbusError):
            await client.read_holding_registers(840, 4)
        await client.close()
    finally:
        server.close()


# --- MQTT codec --------------------------------------------------------------

@pytest.mark.parametrize("n,expected", [(0, b"\x00"), (127, b"\x7f"), (128, b"\x80\x01"), (16383, b"\xff\x7f")])
def test_mqtt_remaining_length_encoding(n, expected):
    assert encode_remaining_length(n) == expected


async def test_mqtt_remaining_length_roundtrip():
    reader = asyncio.StreamReader()
    reader.feed_data(encode_remaining_length(300))
    reader.feed_eof()
    assert await read_remaining_length(reader) == 300


def test_mqtt_connect_will_flags_and_payload():
    from openvan_core.transports.mqtt import build_connect

    frame = build_connect("van", 60, None, None, will_topic="openvan/availability",
                          will_payload=b"offline", will_retain=True)
    body = frame[2:]  # short frame: 1 header + 1 length byte
    flags = body[7]
    assert flags & 0x04  # will flag
    assert flags & 0x20  # will retain
    assert b"openvan/availability" in body and b"offline" in body


def test_mqtt_publish_retain_bit():
    from openvan_core.transports.mqtt import build_publish

    assert build_publish("t", b"x", retain=True)[0] == 0x31
    assert build_publish("t", b"x", retain=False)[0] == 0x30


# --- MQTT loopback -----------------------------------------------------------

async def _mqtt_broker(topic: str, payload: bytes):
    async def handle(reader, writer):
        try:
            # CONNECT → CONNACK(accepted)
            await reader.readexactly(1)
            length = await read_remaining_length(reader)
            await reader.readexactly(length)
            writer.write(bytes([0x20, 0x02, 0x00, 0x00]))
            await writer.drain()
            # SUBSCRIBE → SUBACK
            await reader.readexactly(1)
            length = await read_remaining_length(reader)
            sub = await reader.readexactly(length)
            writer.write(bytes([0x90, 0x03]) + sub[:2] + bytes([0x00]))
            await writer.drain()
            # Publish one value, then hold the connection briefly.
            writer.write(build_publish(topic, payload))
            await writer.drain()
            await asyncio.sleep(0.3)
        except (asyncio.IncompleteReadError, ConnectionError):
            pass

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


async def test_mqtt_client_subscribes_and_receives():
    server, port = await _mqtt_broker("N/abc/system/0/Dc/Battery/Soc", b'{"value": 91.0}')
    async with server:
        client = AsyncMqttClient("127.0.0.1", port)
        await client.connect()
        await client.subscribe("N/#")
        got = None
        async for topic, payload in client.messages():
            got = (topic, payload)
            break
        await client.close()
    assert got is not None
    assert got[0].endswith("Battery/Soc")
    assert b"91.0" in got[1]


async def test_mqtt_pings_even_under_steady_traffic():
    """Keepalive must be driven by time-since-send, not since-read — a busy broker
    (constant inbound) must still get a PINGREQ or it will drop us."""
    got_ping: list[bool] = []

    async def handle(reader, writer):
        try:
            await reader.readexactly(1)  # CONNECT
            await reader.readexactly(await read_remaining_length(reader))
            writer.write(bytes([0x20, 0x02, 0x00, 0x00]))
            await writer.drain()
            await reader.readexactly(1)  # SUBSCRIBE
            sub = await reader.readexactly(await read_remaining_length(reader))
            writer.write(bytes([0x90, 0x03]) + sub[:2] + bytes([0x00]))
            await writer.drain()
            writer.write(build_publish("N/x/system/0/Dc/Battery/Soc", b'{"value": 50}'))
            await writer.drain()
            # Now stay silent and watch for the client's keepalive PINGREQ (0xC0).
            pkt = await asyncio.wait_for(reader.readexactly(1), 2.0)
            if pkt[0] == 0xC0:
                got_ping.append(True)
                await read_remaining_length(reader)
            await asyncio.sleep(0.1)
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError):
            pass

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        client = AsyncMqttClient("127.0.0.1", port, keepalive=1)  # → ping ~0.8 s idle
        await client.connect()
        await client.subscribe("N/#")

        async def drain():
            async for _ in client.messages():
                pass

        task = asyncio.create_task(drain())
        await asyncio.sleep(1.3)  # long enough for one keepalive interval to elapse
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await client.close()
    finally:
        server.close()
    assert got_ping == [True]
