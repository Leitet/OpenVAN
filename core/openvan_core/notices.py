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

import math
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


class FridgeWarm(Advisor):
    key = "fridge_warm"

    def __init__(self, threshold_c: float = 8.0) -> None:
        self.threshold_c = threshold_c

    def evaluate(self, hub: "Hub") -> Notice | None:
        temp = _twin_float(hub, "fridge.temp_c")
        if temp is None or temp < self.threshold_c:
            return None
        return Notice(
            self.key, "warning", "energy", "Fridge warming up",
            f"The fridge is at {temp:.0f}°C — above the food-safe range. Check the "
            f"door, the power, or the setting.",
            {"temp_c": temp},
        )


class FridgeDoorOpen(Advisor):
    key = "fridge_door_open"

    def evaluate(self, hub: "Hub") -> Notice | None:
        if not hub.twin.get("fridge.door_open"):
            return None
        return Notice(
            self.key, "suggestion", "energy", "Fridge door open",
            "The fridge door is open — close it to save the cold and the battery.",
            {},
        )


class LowPropane(Advisor):
    key = "propane_low"

    def __init__(self, threshold: float = 20.0) -> None:
        self.threshold = threshold

    def evaluate(self, hub: "Hub") -> Notice | None:
        level = _entity_value(hub, "sensor.propane_level")
        if level is None or level > self.threshold:
            return None
        return Notice(
            self.key, "suggestion", "climate", "Propane getting low",
            f"The gas bottle is at {level:.0f}%. Plan a swap or refill before it's "
            f"empty mid-meal.",
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


class LongDrive(Advisor):
    """Suggest a break after driving continuously for a while."""

    key = "long_drive"

    def __init__(self, threshold_s: float = 7200.0) -> None:
        self.threshold_s = threshold_s

    def evaluate(self, hub: "Hub") -> Notice | None:
        raw = hub.twin.get("vehicle.trip_seconds")
        if raw is None:
            return None
        try:
            seconds = float(raw)
        except (TypeError, ValueError):
            return None
        if seconds < self.threshold_s:
            return None
        hours = seconds / 3600.0
        return Notice(
            self.key, "suggestion", "journey", "Time for a break?",
            f"You've been driving for about {hours:.1f}h — a short stop might be nice.",
            {"hours": round(hours, 1)},
        )


class RainSoon(Advisor):
    """Warn when rain is approaching (from the weather service)."""

    key = "rain_soon"

    def __init__(self, weather: Any, threshold_h: float = 2.0) -> None:
        self.weather = weather
        self.threshold_h = threshold_h

    def evaluate(self, hub: "Hub") -> Notice | None:
        eta = self.weather.rain_eta_hours()
        if eta is None or eta > self.threshold_h:
            return None
        when = "shortly" if eta < 0.5 else f"in about {eta:g}h"
        return Notice(
            self.key, "suggestion", "weather", "Rain approaching",
            f"Rain is expected {when} — you might want to close up and stow gear.",
            {"eta_hours": eta},
        )


def _twin_float(hub: "Hub", signal: str) -> float | None:
    raw = hub.twin.get(signal)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _dew_point_c(temp_c: float, rh_pct: float) -> float:
    """Dew point (°C) via the Magnus formula. Below this, surfaces sweat."""
    rh = max(1.0, min(100.0, rh_pct))
    a, b = 17.62, 243.12
    gamma = math.log(rh / 100.0) + (a * temp_c) / (b + temp_c)
    return (b * gamma) / (a - gamma)


class CarbonMonoxide(Advisor):
    """The life-critical one. CO is odourless; a sealed cabin fills fast, so this
    is a deterministic edge alarm — never gated on a model (Rule 2)."""

    key = "carbon_monoxide"

    def __init__(self, warn_ppm: float = 35.0, danger_ppm: float = 70.0) -> None:
        self.warn_ppm = warn_ppm
        self.danger_ppm = danger_ppm

    def evaluate(self, hub: "Hub") -> Notice | None:
        ppm = _twin_float(hub, "air.co_ppm")
        if ppm is None or ppm < self.warn_ppm:
            return None
        danger = ppm >= self.danger_ppm
        msg = (
            f"Carbon monoxide is {ppm:.0f} ppm — get fresh air NOW, open up and turn "
            f"off any burner or heater."
            if danger
            else f"Carbon monoxide detected ({ppm:.0f} ppm). Ventilate and check your "
            f"heater/stove."
        )
        return Notice(
            self.key, "warning", "safety", "Carbon monoxide", msg,
            {"ppm": ppm, "danger": danger},
        )


class GasLeak(Advisor):
    """LPG/propane leak — % of the Lower Explosive Limit. An explosive-atmosphere
    alarm, so warn well below the LEL."""

    key = "gas_leak"

    def __init__(self, threshold_lel: float = 10.0) -> None:
        self.threshold_lel = threshold_lel

    def evaluate(self, hub: "Hub") -> Notice | None:
        lel = _twin_float(hub, "air.lpg_pct_lel")
        if lel is None or lel < self.threshold_lel:
            return None
        return Notice(
            self.key, "warning", "safety", "Gas leak",
            f"Propane at {lel:.0f}% LEL — shut the gas off at the bottle, no flames "
            f"or switches, and ventilate.",
            {"pct_lel": lel},
        )


class Smoke(Advisor):
    key = "smoke"

    def evaluate(self, hub: "Hub") -> Notice | None:
        if not hub.twin.get("air.smoke"):
            return None
        return Notice(
            self.key, "warning", "safety", "Smoke detected",
            "Smoke in the cabin — check for fire, and ventilate.",
            {},
        )


class HighCO2(Advisor):
    """Stuffy air. Not dangerous like CO, but 1500 ppm+ means poor sleep and
    headaches — the fix is simply to crack a vent."""

    key = "co2_high"

    def __init__(self, threshold_ppm: float = 1500.0) -> None:
        self.threshold_ppm = threshold_ppm

    def evaluate(self, hub: "Hub") -> Notice | None:
        ppm = _twin_float(hub, "air.co2_ppm")
        if ppm is None or ppm < self.threshold_ppm:
            return None
        return Notice(
            self.key, "suggestion", "climate", "Air getting stuffy",
            f"CO₂ is up to {ppm:.0f} ppm. Crack a window or roof vent for fresher air.",
            {"ppm": ppm},
        )


class Condensation(Advisor):
    """The most *common* van problem: moist cabin air on cold surfaces → damp →
    mould. Fires when the humidity is high and the coldest surface (approximated by
    the outside temperature the walls track) is at or below the dew point."""

    key = "condensation_risk"

    def __init__(self, humidity_floor: float = 60.0, margin_c: float = 1.5) -> None:
        self.humidity_floor = humidity_floor
        self.margin_c = margin_c

    def evaluate(self, hub: "Hub") -> Notice | None:
        rh = _twin_float(hub, "cabin.humidity_pct")
        cabin = _twin_float(hub, "cabin.temperature")
        surface = _twin_float(hub, "outside.temperature")  # walls ~ outside temp
        if rh is None or cabin is None or surface is None:
            return None
        if rh < self.humidity_floor:
            return None
        dew = _dew_point_c(cabin, rh)
        if surface > dew + self.margin_c:
            return None
        return Notice(
            self.key, "suggestion", "climate", "Condensation likely",
            f"Cabin humidity is {rh:.0f}% and surfaces are near the dew point "
            f"({dew:.0f}°C) — expect sweaty windows. Ventilate, or cook/dry outside "
            f"to cut moisture.",
            {"humidity": rh, "dew_point_c": round(dew, 1), "surface_c": surface},
        )


class CabinClimateExtreme(Advisor):
    """When the van is parked, warn on a cabin cold enough to freeze pipes or hot
    enough to endanger pets/passengers left inside."""

    key = "cabin_climate_extreme"

    def __init__(self, cold_c: float = 3.0, hot_c: float = 30.0) -> None:
        self.cold_c = cold_c
        self.hot_c = hot_c

    def evaluate(self, hub: "Hub") -> Notice | None:
        if hub.twin.get("vehicle.ignition"):
            return None  # driving — climate is being managed
        cabin = _twin_float(hub, "cabin.temperature")
        if cabin is None:
            return None
        if cabin <= self.cold_c:
            return Notice(
                self.key, "warning", "climate", "Cabin freezing",
                f"It's {cabin:.0f}°C inside — risk to water pipes (and anyone/anything "
                f"aboard). Consider some heat.",
                {"cabin_c": cabin, "kind": "cold"},
            )
        if cabin >= self.hot_c:
            return Notice(
                self.key, "warning", "climate", "Cabin too hot",
                f"It's {cabin:.0f}°C inside — dangerous for pets or passengers. "
                f"Ventilate or move to shade.",
                {"cabin_c": cabin, "kind": "hot"},
            )
        return None


def leveling_advice(
    pitch_deg: float,
    roll_deg: float,
    *,
    threshold_deg: float = 1.5,
    track_m: float = 2.0,
    wheelbase_m: float = 3.6,
) -> dict[str, Any] | None:
    """Turn pitch/roll into how much to raise which side/end. Returns None when the
    van is level enough. pitch>0 = nose up (raise rear); roll>0 = right low (raise
    right). Shared shape with the UI's bubble level."""
    if abs(pitch_deg) < threshold_deg and abs(roll_deg) < threshold_deg:
        return None
    parts: list[str] = []
    roll_cm = math.tan(math.radians(abs(roll_deg))) * track_m * 100
    pitch_cm = math.tan(math.radians(abs(pitch_deg))) * wheelbase_m * 100
    side = end = None
    if abs(roll_deg) >= threshold_deg:
        side = "right" if roll_deg > 0 else "left"
        parts.append(f"raise the {side} side about {roll_cm:.0f} cm")
    if abs(pitch_deg) >= threshold_deg:
        end = "rear" if pitch_deg > 0 else "front"
        parts.append(f"raise the {end} about {pitch_cm:.0f} cm")
    return {
        "tilt_deg": round(max(abs(pitch_deg), abs(roll_deg)), 1),
        "raise_side": side,
        "raise_end": end,
        "roll_cm": round(roll_cm),
        "pitch_cm": round(pitch_cm),
        "text": " and ".join(parts),
    }


class NotLevel(Advisor):
    """When parked, nudge the driver to level up for a comfortable night."""

    key = "not_level"

    def __init__(self, threshold_deg: float = 1.5) -> None:
        self.threshold_deg = threshold_deg

    def evaluate(self, hub: "Hub") -> Notice | None:
        if hub.twin.get("vehicle.ignition"):
            return None  # only worth saying once you've stopped to park
        pitch = _twin_float(hub, "imu.pitch_deg")
        roll = _twin_float(hub, "imu.roll_deg")
        if pitch is None or roll is None:
            return None
        advice = leveling_advice(pitch, roll, threshold_deg=self.threshold_deg)
        if advice is None:
            return None
        return Notice(
            self.key, "suggestion", "journey", "Not quite level",
            f"You're {advice['tilt_deg']}° off level — {advice['text']} for a flat night.",
            advice,
        )


class Intrusion(Advisor):
    """When 'away mode' is armed, a door or motion event is a security alert."""

    key = "intrusion"

    def __init__(self, security: Any) -> None:
        self.security = security

    def evaluate(self, hub: "Hub") -> Notice | None:
        if not self.security.is_armed():
            return None
        door = hub.twin.get("security.door_open")
        motion = hub.twin.get("security.motion")
        if not (door or motion):
            return None
        what = "a door opened" if door else "motion was seen"
        return Notice(
            self.key, "warning", "safety", "Security alert",
            f"While away mode is armed, {what} inside the van. Check on it.",
            {"door": bool(door), "motion": bool(motion)},
        )


class ServiceDue(Advisor):
    """Surface any maintenance item that's due or overdue (odometer or date based)."""

    key = "service_due"

    def __init__(self, log: Any) -> None:
        self.log = log

    def evaluate(self, hub: "Hub") -> Notice | None:
        from datetime import datetime

        odo = _twin_float(hub, "vehicle.odometer_km")
        due = [s for s in self.log.status(odo, datetime.now().date()) if s["due"]]
        if not due:
            return None
        labels = ", ".join(s["label"] for s in due)
        return Notice(
            self.key, "suggestion", "journey", "Maintenance due",
            f"Due now: {labels}. Tick it off once done.",
            {"items": [s["id"] for s in due]},
        )


def default_advisors() -> list[Advisor]:
    return [
        LowFreshWater(),
        GreyWaterFull(),
        LowDiesel(),
        LowPropane(),
        FridgeWarm(),
        FridgeDoorOpen(),
        BatteryRuntime(),
        LongDrive(),
        # Air & safety (life-critical → most-common)
        CarbonMonoxide(),
        GasLeak(),
        Smoke(),
        HighCO2(),
        Condensation(),
        CabinClimateExtreme(),
        NotLevel(),
    ]


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
        self._unsubscribers.append(
            self.bus.subscribe("weather.updated", self._on_change)
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
