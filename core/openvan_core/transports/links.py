"""Serial links — many ways to reach a wire, chosen like drivers.

A van's "serial device" (heater blue-wire, Votronic display bus, an RS-485
charge controller) can be physically reached several ways, and an OS for vans
must support them all as *options*, not pick one dependency:

* ``tcp`` — a TCP↔serial bridge (Elfin EW11, USR-TCP232, ser2net, ESPHome
  stream server). **Pure stdlib**, and in practice the most common way the
  smart-van community wires RS-485/UART gear in. Works today, no extras.
* ``serial`` — a directly attached USB/UART port (``/dev/ttyUSB0``) via
  **pyserial-asyncio**, an optional extra (``pip install -e ".[serial]"``) so
  the core stays light.
* ``sim`` — the Rule-1 stand-in: a scripted link the bench/tests drive.

Drivers ask the factory for a link from their config (``link``/``host``/
``port``/``device``/``baud``) and speak their protocol over the same
reader/writer shape regardless of how the bytes travel. New link types register
in :data:`LINK_TYPES` — extensible, like everything else here.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Callable

DEFAULT_BAUD = 115200


class SerialLink(ABC):
    """A byte pipe to a device, however it is reached."""

    kind: str = "link"

    @abstractmethod
    async def open(self) -> None:
        ...

    @abstractmethod
    async def write(self, data: bytes) -> None:
        ...

    @abstractmethod
    async def read(self, max_bytes: int = 256, timeout: float = 1.0) -> bytes:
        """Up to ``max_bytes`` (at least 1 unless timeout) — b"" on timeout."""

    @abstractmethod
    async def close(self) -> None:
        ...


class SimSerialLink(SerialLink):
    """Scripted stand-in: tests/bench feed responses, writes are recorded, and an
    optional responder turns a request into a scripted reply (a fake device)."""

    kind = "sim"

    def __init__(self, responder: Callable[[bytes], bytes | None] | None = None) -> None:
        self._responder = responder
        self._rx: asyncio.Queue[bytes] = asyncio.Queue()
        self.writes: list[bytes] = []
        self.opened = False

    async def open(self) -> None:
        self.opened = True

    def feed(self, data: bytes) -> None:
        self._rx.put_nowait(data)

    async def write(self, data: bytes) -> None:
        self.writes.append(data)
        if self._responder is not None:
            reply = self._responder(data)
            if reply:
                self._rx.put_nowait(reply)

    async def read(self, max_bytes: int = 256, timeout: float = 1.0) -> bytes:
        try:
            data = await asyncio.wait_for(self._rx.get(), timeout)
        except asyncio.TimeoutError:
            return b""
        return data[:max_bytes]

    async def close(self) -> None:
        self.opened = False


class _StreamLink(SerialLink):
    """Common reader/writer plumbing for TCP bridges and pyserial."""

    def __init__(self) -> None:
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def write(self, data: bytes) -> None:
        if self._writer is None:
            raise ConnectionError("link not open")
        self._writer.write(data)
        await self._writer.drain()

    async def read(self, max_bytes: int = 256, timeout: float = 1.0) -> bytes:
        if self._reader is None:
            raise ConnectionError("link not open")
        try:
            return await asyncio.wait_for(self._reader.read(max_bytes), timeout)
        except asyncio.TimeoutError:
            return b""

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except (OSError, asyncio.CancelledError):
                pass
        self._reader = self._writer = None


class TcpSerialLink(_StreamLink):
    """A serial device behind a TCP bridge (EW11, ser2net, ESPHome stream server).
    Pure stdlib — the zero-dependency way to reach RS-485/UART hardware."""

    kind = "tcp"

    def __init__(self, host: str, port: int) -> None:
        super().__init__()
        self.host = host
        self.port = port

    async def open(self) -> None:
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), 10.0
        )


class PyserialLink(_StreamLink):
    """A directly attached port via pyserial-asyncio (optional `serial` extra)."""

    kind = "serial"

    def __init__(self, device: str, baud: int = DEFAULT_BAUD) -> None:
        super().__init__()
        self.device = device
        self.baud = baud

    async def open(self) -> None:  # pragma: no cover - needs a real port
        from serial_asyncio import open_serial_connection  # optional extra

        self._reader, self._writer = await open_serial_connection(
            url=self.device, baudrate=self.baud
        )


def _make_sim(config: dict[str, Any]) -> SerialLink:
    return SimSerialLink()


def _make_tcp(config: dict[str, Any]) -> SerialLink:
    host = str(config.get("host") or "")
    if not host:
        raise ValueError("tcp link needs a host")
    return TcpSerialLink(host, int(config.get("port") or 8899))  # EW11's default


def _make_serial(config: dict[str, Any]) -> SerialLink:
    device = str(config.get("device") or "")
    if not device:
        raise ValueError("serial link needs a device path")
    return PyserialLink(device, int(config.get("baud") or DEFAULT_BAUD))


# Extensible registry — new ways to reach a wire slot in like drivers do.
LINK_TYPES: dict[str, Callable[[dict[str, Any]], SerialLink]] = {
    "sim": _make_sim,
    "tcp": _make_tcp,
    "serial": _make_serial,
}


def create_link(config: dict[str, Any]) -> SerialLink:
    """Build the configured link (``link``: sim | tcp | serial | …)."""
    kind = str(config.get("link") or "tcp")
    factory = LINK_TYPES.get(kind)
    if factory is None:
        raise ValueError(f"unknown link type '{kind}' (have: {sorted(LINK_TYPES)})")
    return factory(config)
