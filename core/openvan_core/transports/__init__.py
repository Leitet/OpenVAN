"""Real hardware transports — the wire under the integration drivers.

Pure-stdlib async clients (no vendor SDKs, no third-party deps) so the edge
runtime stays small. Each speaks one protocol and is verifiable offline against an
in-process loopback server (see ``tests/``): the protocol codecs are exact to the
spec, and the byte framing is unit-tested.

An integration in a real mode connects through one of these and streams normalised
signals into the twin; when no device is reachable it falls back to the driver's
``simulate()`` (offline-first, Rule 3).
"""

from __future__ import annotations

from .modbus_tcp import AsyncModbusTcpClient, ModbusError
from .mqtt import AsyncMqttClient, MqttError

__all__ = [
    "AsyncModbusTcpClient",
    "ModbusError",
    "AsyncMqttClient",
    "MqttError",
]
