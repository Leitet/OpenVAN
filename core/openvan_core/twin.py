"""The digital twin of the physical van.

Since there is (yet) no physical van, the ``VanTwin`` holds the raw hardware
signals that real sensors and actuators would produce: battery voltage, solar
watts, water litres, cabin temperature, actuator on/off states, and so on.

The web simulator drives these signals (injecting sensor readings, observing
actuator effects). Plugins never touch the twin directly — they go through a
:class:`~openvan_core.backends.Backend`, which is what makes the very same
plugin code run against the simulator today and real hardware tomorrow.
"""

from __future__ import annotations

from typing import Any

from .events import EventBus

SIGNAL_CHANGED = "twin.signal_changed"


class VanTwin:
    """Key/value store of raw device signals with change notification."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._signals: dict[str, Any] = {}

    async def set_signal(self, key: str, value: Any, source: str = "sim") -> None:
        changed = self._signals.get(key) != value
        self._signals[key] = value
        if changed:
            await self._bus.publish(
                SIGNAL_CHANGED, {"key": key, "value": value, "source": source}
            )

    def get(self, key: str, default: Any = None) -> Any:
        return self._signals.get(key, default)

    def snapshot(self) -> dict[str, Any]:
        return dict(self._signals)
