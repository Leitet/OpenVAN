"""Minimal async Modbus-TCP client — pure stdlib.

Modbus-TCP is a small, well-documented binary protocol: a 7-byte MBAP header
(transaction id, protocol id, length, unit id) followed by a PDU (function code +
data). We implement the two read functions an integration needs — Read Holding
Registers (0x03) and Read Input Registers (0x04) — which is enough to poll a
Victron GX, an EPEver/EPsolar MPPT, a generic energy meter, and most Modbus kit.

No third-party dependency (no pymodbus): the framing is exact to the spec and
verified against an in-process loopback server in the tests. Register *maps* are
device data and live in each integration, not here.
"""

from __future__ import annotations

import asyncio
import struct

# Function codes we support (read-only — writing to a van's energy bus is a
# safety-class decision made in the integration, not a bare transport call).
READ_HOLDING_REGISTERS = 0x03
READ_INPUT_REGISTERS = 0x04


class ModbusError(Exception):
    """A Modbus exception response or a malformed frame."""


# Modbus exception codes → human text (subset that matters in practice).
_EXCEPTION_TEXT = {
    0x01: "illegal function",
    0x02: "illegal data address",
    0x03: "illegal data value",
    0x04: "server device failure",
    0x06: "server device busy",
}


def build_read_request(transaction_id: int, unit_id: int, function: int, address: int, count: int) -> bytes:
    """Encode a read-registers ADU (MBAP header + PDU). Public for codec tests."""
    pdu = struct.pack(">BHH", function, address, count)
    # MBAP length counts the unit id + PDU.
    mbap = struct.pack(">HHHB", transaction_id & 0xFFFF, 0, len(pdu) + 1, unit_id & 0xFF)
    return mbap + pdu


def parse_read_response(payload: bytes, function: int, count: int) -> list[int]:
    """Decode a read-registers PDU body (function code onward) into register words.

    Raises :class:`ModbusError` on an exception response or a length mismatch.
    """
    if len(payload) < 2:
        raise ModbusError("short response")
    resp_fn = payload[0]
    if resp_fn == (function | 0x80):  # exception response
        code = payload[1]
        raise ModbusError(f"modbus exception 0x{code:02x}: {_EXCEPTION_TEXT.get(code, 'unknown')}")
    if resp_fn != function:
        raise ModbusError(f"unexpected function 0x{resp_fn:02x} (wanted 0x{function:02x})")
    byte_count = payload[1]
    if byte_count != count * 2 or len(payload) < 2 + byte_count:
        raise ModbusError("register byte-count mismatch")
    return list(struct.unpack(f">{count}H", payload[2 : 2 + byte_count]))


class AsyncModbusTcpClient:
    """A single-connection async Modbus-TCP master.

    Usage::

        client = AsyncModbusTcpClient("192.168.1.20", unit_id=100)
        await client.connect()
        regs = await client.read_holding_registers(840, 4)
        await client.close()
    """

    def __init__(self, host: str, port: int = 502, unit_id: int = 1, timeout: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._tid = 0
        self._lock = asyncio.Lock()  # one in-flight transaction at a time

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), self.timeout
        )

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except (OSError, asyncio.CancelledError):
                pass
        self._reader = self._writer = None

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        return await self._read(READ_HOLDING_REGISTERS, address, count)

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        return await self._read(READ_INPUT_REGISTERS, address, count)

    async def _read(self, function: int, address: int, count: int) -> list[int]:
        if self._writer is None or self._reader is None:
            raise ModbusError("not connected")
        if not 1 <= count <= 125:
            raise ModbusError("register count out of range (1..125)")
        async with self._lock:
            self._tid = (self._tid + 1) & 0xFFFF
            tid = self._tid
            self._writer.write(build_read_request(tid, self.unit_id, function, address, count))
            await self._writer.drain()

            header = await asyncio.wait_for(self._reader.readexactly(7), self.timeout)
            resp_tid, proto, length, _unit = struct.unpack(">HHHB", header)
            if proto != 0:
                raise ModbusError(f"bad protocol id {proto}")
            if resp_tid != tid:
                raise ModbusError("transaction id mismatch")
            if length < 2:  # must cover unit id + at least a function-code byte
                raise ModbusError(f"invalid MBAP length {length}")
            body = await asyncio.wait_for(self._reader.readexactly(length - 1), self.timeout)
        return parse_read_response(body, function, count)


# --- register value helpers (used by integration normalisers) ----------------

def to_int16(word: int) -> int:
    """Interpret an unsigned register word as a signed 16-bit value."""
    return word - 0x10000 if word >= 0x8000 else word


def to_int32(hi: int, lo: int) -> int:
    """Two big-endian words → signed 32-bit."""
    value = (hi << 16) | lo
    return value - 0x1_0000_0000 if value >= 0x8000_0000 else value


def to_uint32(hi: int, lo: int) -> int:
    return (hi << 16) | lo
