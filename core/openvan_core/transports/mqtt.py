"""Minimal async MQTT 3.1.1 subscriber — pure stdlib.

Enough of MQTT to *consume* a broker: CONNECT, SUBSCRIBE, receive PUBLISH, and
keep the connection alive with PINGREQ. That covers the read side of Victron Venus
OS (which publishes to ``N/<portal>/...``), Home Assistant's MQTT discovery, ESPHome
over MQTT, Shelly, and Tasmota — the ecosystems that matter for OpenVan.

No paho / aiomqtt dependency: the control-packet codec is exact to the 3.1.1 spec
and verified against an in-process loopback broker in the tests. We publish too
(needed for Victron's keepalive request topic), but only QoS-0 — no session state,
no QoS-1/2 acknowledgement bookkeeping, which keeps the edge runtime small.
"""

from __future__ import annotations

import asyncio
import struct
import time
from typing import AsyncIterator

# Control packet types (high nibble of the fixed header).
CONNECT = 0x10
CONNACK = 0x20
PUBLISH = 0x30
SUBSCRIBE = 0x82  # includes the required 0b0010 flags
SUBACK = 0x90
PINGREQ = 0xC0
PINGRESP = 0xD0
DISCONNECT = 0xE0


class MqttError(Exception):
    """A protocol error or a rejected connection."""


# --- codec (public for tests) ------------------------------------------------

def encode_remaining_length(length: int) -> bytes:
    """MQTT variable-length integer (7 bits/byte, high bit = continuation)."""
    out = bytearray()
    while True:
        byte = length % 128
        length //= 128
        if length > 0:
            byte |= 0x80
        out.append(byte)
        if length == 0:
            return bytes(out)


async def read_remaining_length(reader: asyncio.StreamReader) -> int:
    multiplier = 1
    value = 0
    for _ in range(4):
        (byte,) = struct.unpack("!B", await reader.readexactly(1))
        value += (byte & 0x7F) * multiplier
        if not byte & 0x80:
            return value
        multiplier *= 128
    raise MqttError("malformed remaining length")


def _encode_string(s: str) -> bytes:
    raw = s.encode("utf-8")
    return struct.pack("!H", len(raw)) + raw


def build_connect(
    client_id: str,
    keepalive: int,
    username: str | None,
    password: str | None,
    will_topic: str | None = None,
    will_payload: bytes = b"",
    will_retain: bool = True,
) -> bytes:
    """A Last Will lets the broker announce our death (e.g. availability=offline
    retained) when the connection drops without a clean DISCONNECT."""
    flags = 0x02  # clean session
    payload = _encode_string(client_id)
    if will_topic:
        flags |= 0x04  # will flag, QoS 0
        if will_retain:
            flags |= 0x20
        payload += _encode_string(will_topic)
        payload += struct.pack("!H", len(will_payload)) + will_payload
    if username:
        flags |= 0x80
        payload += _encode_string(username)
        if password:
            flags |= 0x40
            payload += _encode_string(password)
    var_header = _encode_string("MQTT") + bytes([0x04, flags]) + struct.pack("!H", keepalive)
    body = var_header + payload
    return bytes([CONNECT]) + encode_remaining_length(len(body)) + body


def build_subscribe(packet_id: int, topic: str, qos: int = 0) -> bytes:
    body = struct.pack("!H", packet_id) + _encode_string(topic) + bytes([qos])
    return bytes([SUBSCRIBE]) + encode_remaining_length(len(body)) + body


def build_publish(topic: str, payload: bytes, retain: bool = False) -> bytes:
    body = _encode_string(topic) + payload  # QoS 0 → no packet id
    header = PUBLISH | (0x01 if retain else 0x00)
    return bytes([header]) + encode_remaining_length(len(body)) + body


def parse_publish(body: bytes, qos: int) -> tuple[str, bytes]:
    (topic_len,) = struct.unpack("!H", body[:2])
    topic = body[2 : 2 + topic_len].decode("utf-8", "replace")
    rest = body[2 + topic_len :]
    if qos > 0:  # skip the packet identifier
        rest = rest[2:]
    return topic, rest


class AsyncMqttClient:
    """A single-connection async MQTT subscriber.

    Usage::

        client = AsyncMqttClient("192.168.1.20")
        await client.connect()
        await client.subscribe("N/#")
        async for topic, payload in client.messages():
            ...
    """

    def __init__(
        self,
        host: str,
        port: int = 1883,
        client_id: str = "openvan",
        keepalive: int = 60,
        username: str | None = None,
        password: str | None = None,
        timeout: float = 5.0,
        will_topic: str | None = None,
        will_payload: bytes = b"",
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.keepalive = keepalive
        self.username = username
        self.password = password
        self.timeout = timeout
        self.will_topic = will_topic
        self.will_payload = will_payload
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._packet_id = 0
        self._last_send = 0.0  # monotonic time of our last outbound packet

    async def _send(self, data: bytes) -> None:
        assert self._writer is not None
        self._writer.write(data)
        await self._writer.drain()
        self._last_send = time.monotonic()

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), self.timeout
        )
        await self._send(
            build_connect(
                self.client_id, self.keepalive, self.username, self.password,
                will_topic=self.will_topic, will_payload=self.will_payload,
            )
        )
        fixed = await asyncio.wait_for(self._reader.readexactly(1), self.timeout)
        if fixed[0] != CONNACK:
            raise MqttError(f"expected CONNACK, got 0x{fixed[0]:02x}")
        length = await read_remaining_length(self._reader)
        body = await self._reader.readexactly(length)
        if len(body) < 2 or body[1] != 0x00:
            raise MqttError(f"connection refused (code {body[1] if len(body) > 1 else '?'})")

    async def subscribe(self, topic: str, qos: int = 0) -> None:
        if self._writer is None:
            raise MqttError("not connected")
        self._packet_id = (self._packet_id % 0xFFFF) + 1
        await self._send(build_subscribe(self._packet_id, topic, qos))

    async def publish(self, topic: str, payload: bytes, retain: bool = False) -> None:
        if self._writer is None:
            raise MqttError("not connected")
        await self._send(build_publish(topic, payload, retain))

    async def _ping(self) -> None:
        if self._writer is not None:
            await self._send(bytes([PINGREQ, 0x00]))

    async def messages(self) -> AsyncIterator[tuple[str, bytes]]:
        """Yield ``(topic, payload)`` for each PUBLISH until the connection drops.

        Keeps the link alive with PINGREQ within the keepalive interval — gated on
        time since our last *send*, not since the last read, so a busy broker (which
        keeps us receiving) doesn't starve the ping and get dropped. Silently consumes
        SUBACK / PINGRESP control packets.
        """
        if self._reader is None:
            raise MqttError("not connected")
        interval = self.keepalive * 0.8 if self.keepalive else None
        while True:
            timeout = None
            if interval is not None:
                timeout = max(0.05, interval - (time.monotonic() - self._last_send))
            try:
                fixed = await asyncio.wait_for(self._reader.readexactly(1), timeout)
            except asyncio.TimeoutError:
                await self._ping()
                continue
            except asyncio.IncompleteReadError:
                return  # broker closed the connection
            packet_type = fixed[0] & 0xF0
            length = await read_remaining_length(self._reader)
            body = await self._reader.readexactly(length) if length else b""
            if packet_type == PUBLISH:
                qos = (fixed[0] & 0x06) >> 1
                yield parse_publish(body, qos)
            # SUBACK / PINGRESP / others: nothing to surface, keep reading.
            # Even while receiving steadily, ping if we've been silent too long.
            if interval is not None and (time.monotonic() - self._last_send) >= interval:
                await self._ping()

    async def close(self) -> None:
        if self._writer is not None:
            try:
                self._writer.write(bytes([DISCONNECT, 0x00]))
                await self._writer.drain()
            except (OSError, ConnectionError):
                pass
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except (OSError, asyncio.CancelledError):
                pass
        self._reader = self._writer = None
