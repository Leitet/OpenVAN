"""Modbus RTU over any :mod:`links` serial link — pure stdlib.

RTU is the framing RS-485 gear actually speaks (EPEver/EPsolar, Votronic-adjacent
kit, cheap meters): ``[addr][func][data][crc16-lo][crc16-hi]``. Combined with the
link layer, the same client reaches hardware through a TCP bridge (EW11/ser2net —
no dependencies), a USB adapter (optional ``serial`` extra) or the sim link.

Read-only (functions 0x03/0x04), like the Modbus-TCP client — writes to an energy
bus are a safety-layer decision made in a driver, never a bare transport call.
"""

from __future__ import annotations

import asyncio
import struct

from .links import SerialLink

READ_HOLDING_REGISTERS = 0x03
READ_INPUT_REGISTERS = 0x04


class ModbusRtuError(Exception):
    """A Modbus exception response, CRC failure or malformed frame."""


def crc16(data: bytes) -> int:
    """Modbus CRC-16 (poly 0xA001, init 0xFFFF)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            lsb = crc & 1
            crc >>= 1
            if lsb:
                crc ^= 0xA001
    return crc


def build_read_request(unit_id: int, function: int, address: int, count: int) -> bytes:
    body = struct.pack(">BBHH", unit_id & 0xFF, function, address, count)
    return body + struct.pack("<H", crc16(body))


def parse_read_response(frame: bytes, unit_id: int, function: int, count: int) -> list[int]:
    if len(frame) < 5:
        raise ModbusRtuError("short frame")
    body, crc = frame[:-2], struct.unpack("<H", frame[-2:])[0]
    if crc16(body) != crc:
        raise ModbusRtuError("CRC mismatch")
    if body[0] != unit_id:
        raise ModbusRtuError(f"unexpected unit id {body[0]}")
    if body[1] == (function | 0x80):
        raise ModbusRtuError(f"modbus exception 0x{body[2]:02x}")
    if body[1] != function or body[2] != count * 2 or len(body) != 3 + count * 2:
        raise ModbusRtuError("malformed response")
    return list(struct.unpack(f">{count}H", body[3:]))


class AsyncModbusRtuClient:
    """A single-master RTU client over a :class:`SerialLink`."""

    def __init__(self, link: SerialLink, unit_id: int = 1, timeout: float = 2.0) -> None:
        self.link = link
        self.unit_id = unit_id
        self.timeout = timeout
        self._lock = asyncio.Lock()

    async def open(self) -> None:
        await self.link.open()

    async def close(self) -> None:
        await self.link.close()

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        return await self._read(READ_HOLDING_REGISTERS, address, count)

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        return await self._read(READ_INPUT_REGISTERS, address, count)

    async def _read(self, function: int, address: int, count: int) -> list[int]:
        if not 1 <= count <= 125:
            raise ModbusRtuError("register count out of range (1..125)")
        expected = 5 + count * 2  # addr+func+len + payload + crc
        async with self._lock:
            await self.link.write(build_read_request(self.unit_id, function, address, count))
            frame = bytearray()
            # Accumulate until a full frame or the timeout window closes — RTU has
            # no length prefix on the wire beyond the byte-count field.
            deadline = asyncio.get_event_loop().time() + self.timeout
            while len(frame) < expected:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    break
                chunk = await self.link.read(expected - len(frame), timeout=remaining)
                if not chunk:
                    break
                frame += chunk
                # An exception response is only 5 bytes — stop early if it checks out.
                if len(frame) == 5 and frame[1] & 0x80:
                    break
        if not frame:
            raise ModbusRtuError("no response (check link/wiring/unit id)")
        return parse_read_response(bytes(frame), self.unit_id, function, count)
