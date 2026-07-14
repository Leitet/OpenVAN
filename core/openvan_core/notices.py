"""Proactive companion notices.

OpenVan should feel like a travel companion, not a control panel — so it watches
the van's state and speaks up *before* being asked: fresh water getting low, the
grey tank nearly full, the battery unlikely to last the night, diesel running out.

Advisors are deterministic and offline-first (simple thresholds over live state),
mirroring the safety layer. The :class:`AdvisorEngine` is edge-triggered: it emits
``notice.created`` when a condition starts holding and ``notice.cleared`` when it
stops, so the companion never nags every tick. Warm phrasing (the "good morning…"
briefing) is a separate, optional LLM layer — see ``companion.py``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from .events import EventBus

if TYPE_CHECKING:  # pragma: no cover
    from .hub import Hub


@dataclass
class Notice:
    key: str  # stable dedup key, e.g. "fresh_water_low"
    level: str  # "info" | "suggestion" | "warning"
    category: str  # "energy" | "water" | "climate" | "journey"
    title: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "level": self.level,
            "category": self.category,
            "title": self.title,
            "message": self.message,
            "data": dict(self.data),
        }


class Advisor(ABC):
    key: str = "advisor"

    @abstractmethod
    def evaluate(self, hub: "Hub") -> Notice | None:
        """Return a Notice while its condition holds, else None."""


def _entity_value(hub: "Hub", entity_id: str) -> float | None:
    entity = hub.get_entity(entity_id)
    if entity is None or entity.state is None:
        return None
    try:
        return float(entity.state)
    except (TypeError, ValueError):
        return None


class LowFreshWater(Advisor):
    key = "fresh_water_low"

    def __init__(self, threshold: float = 15.0) -> None:
        self.threshold = threshold

    def evaluate(self, hub: "Hub") -> Notice | None:
        level = _entity_value(hub, "sensor.fresh_water_level")
        if level is None or level > self.threshold:
            return None
        return Notice(
            self.key, "warning", "water", "Fresh water low",
            f"Fresh water is down to {level:.0f}%. Worth planning a refill soon.",
            {"level": level},
        )


class GreyWaterFull(Advisor):
    key = "grey_water_full"

    def __init__(self, threshold: float = 85.0) -> None:
        self.threshold = threshold

    def evaluate(self, hub: "Hub") -> Notice | None:
        level = _entity_value(hub, "sensor.grey_water_level")
        if level is None or level < self.threshold:
            return None
        return Notice(
            self.key, "warning", "water", "Grey tank almost full",
            f"The grey water tank is at {level:.0f}%. Time to find a dump point.",
            {"level": level},
        )


class LowDiesel(Advisor):
    key = "diesel_low"

    def __init__(self, threshold: float = 15.0) -> None:
        self.threshold = threshold

    def evaluate(self, hub: "Hub") -> Notice | None:
        raw = hub.twin.get("diesel_tank.level_pct")
        if raw is None:
            return None
        try:
            level = float(raw)
        except (TypeError, ValueError):
            return None
        if level > self.threshold:
            return None
        return Notice(
            self.key, "suggestion", "climate", "Diesel getting low",
            f"Diesel is at {level:.0f}%. Top up before the next cold night.",
            {"level": level},
        )


class BatteryRuntime(Advisor):
    """Warn when the house battery is unlikely to last much longer at current draw."""

    key = "battery_runtime_low"

    def __init__(self, capacity_ah: float = 200.0, low_hours: float = 24.0) -> None:
        self.capacity_ah = capacity_ah
        self.low_hours = low_hours

    def evaluate(self, hub: "Hub") -> Notice | None:
        soc = _entity_value(hub, "sensor.house_battery_soc")
        current = _entity_value(hub, "sensor.house_battery_current")
        if soc is None or current is None or current >= -0.05:
            return None  # charging or idle — nothing to warn about
        hours = self.capacity_ah * (soc / 100.0) / abs(current)
        if hours > self.low_hours:
            return None
        return Notice(
            self.key, "warning", "energy", "Battery running low",
            f"At the current draw the battery should last about {hours:.0f}h. "
            f"Consider charging or shedding load.",
            {"hours": round(hours, 1), "soc": soc},
        )


def default_advisors() -> list[Advisor]:
    return [LowFreshWater(), GreyWaterFull(), LowDiesel(), BatteryRuntime()]


class AdvisorEngine:
    """Runs advisors on state changes and emits edge-triggered notices."""

    def __init__(self, bus: EventBus, hub: "Hub", advisors: list[Advisor] | None = None) -> None:
        self.bus = bus
        self.hub = hub
        self.advisors = advisors if advisors is not None else default_advisors()
        self._active: dict[str, Notice] = {}
        self._unsubscribers: list[Callable[[], None]] = []

    def start(self) -> None:
        self._unsubscribers.append(
            self.bus.subscribe("entity.state_changed", self._on_change)
        )
        self._unsubscribers.append(
            self.bus.subscribe("twin.signal_changed", self._on_change)
        )

    async def _on_change(self, _event) -> None:
        await self.evaluate()

    async def evaluate(self) -> None:
        firing: set[str] = set()
        for advisor in self.advisors:
            notice = advisor.evaluate(self.hub)
            if notice is None:
                continue
            firing.add(notice.key)
            is_new = notice.key not in self._active
            self._active[notice.key] = notice
            if is_new:
                await self.bus.publish("notice.created", {"notice": notice.as_dict()})
        for key in list(self._active):
            if key not in firing:
                cleared = self._active.pop(key)
                await self.bus.publish("notice.cleared", {"notice": cleared.as_dict()})

    def active_notices(self) -> list[dict[str, Any]]:
        return [n.as_dict() for n in self._active.values()]

    async def stop(self) -> None:
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
