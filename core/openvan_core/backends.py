"""Hardware I/O seam.

A ``Backend`` is how a plugin reads sensors and drives actuators. This is the
single seam that separates simulation from reality:

* :class:`SimBackend` maps reads/writes onto the :class:`~openvan_core.twin.VanTwin`.
* A future ``VictronBackend`` / ``ModbusBackend`` / ``CanBackend`` would implement
  the same interface against real hardware.

Because plugins depend only on this interface, "add simulator support" is not
extra work bolted on afterwards — it is the default execution path.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable

from .events import EventBus
from .twin import SIGNAL_CHANGED, VanTwin

SignalHandler = Callable[[str, Any], Awaitable[None]]


class Backend(ABC):
    @abstractmethod
    async def read(self, key: str, default: Any = None) -> Any:
        ...

    @abstractmethod
    async def write(self, key: str, value: Any) -> None:
        ...

    @abstractmethod
    def watch(self, key: str, handler: SignalHandler) -> Callable[[], None]:
        """Call ``handler(key, value)`` whenever ``key`` changes. Returns unwatch."""


class SimBackend(Backend):
    """Backend implementation driven by the simulated van twin."""

    def __init__(self, bus: EventBus, twin: VanTwin) -> None:
        self._bus = bus
        self._twin = twin

    async def read(self, key: str, default: Any = None) -> Any:
        return self._twin.get(key, default)

    async def write(self, key: str, value: Any) -> None:
        # A write from a plugin (e.g. turning a light on) is an actuator effect;
        # tag the source so the simulator can distinguish it from user injection.
        await self._twin.set_signal(key, value, source="plugin")

    def watch(self, key: str, handler: SignalHandler) -> Callable[[], None]:
        async def _on_event(event) -> None:
            if event.data.get("key") == key:
                await handler(key, event.data.get("value"))

        return self._bus.subscribe(SIGNAL_CHANGED, _on_event)
