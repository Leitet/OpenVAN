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
STALE_CHANGED = "twin.stale_changed"


class VanTwin:
    """Key/value store of raw device signals with change notification."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._signals: dict[str, Any] = {}
        # Last writer per key (integration id / plugin domain / "seed" / "sim").
        # Lets the bench group and auto-generate injectors per data source — the
        # plug-and-play counterpart of the product UI's auto entities.
        self._sources: dict[str, str] = {}
        # Keys whose last value is STALE — the transport that provided them
        # dropped, so the reading is frozen history, not a current measurement.
        # A fresh write clears the flag.
        self._stale: set[str] = set()

    async def set_signal(self, key: str, value: Any, source: str = "sim") -> None:
        changed = self._signals.get(key) != value
        self._signals[key] = value
        self._sources[key] = source
        if key in self._stale:
            self._stale.discard(key)
            await self._bus.publish(STALE_CHANGED, {"keys": [key], "stale": False})
        if changed:
            await self._bus.publish(
                SIGNAL_CHANGED, {"key": key, "value": value, "source": source}
            )

    def get(self, key: str, default: Any = None) -> Any:
        return self._signals.get(key, default)

    def snapshot(self) -> dict[str, Any]:
        return dict(self._signals)

    def sources(self) -> dict[str, str]:
        return dict(self._sources)

    async def mark_stale(self, keys: list[str]) -> None:
        """Flag signals as stale (their provider dropped). Values stay visible —
        last-known is useful — but honestly marked, never shown as current."""
        fresh = [k for k in keys if k in self._signals and k not in self._stale]
        if not fresh:
            return
        self._stale.update(fresh)
        await self._bus.publish(STALE_CHANGED, {"keys": fresh, "stale": True})

    def stale(self) -> list[str]:
        return sorted(self._stale)
