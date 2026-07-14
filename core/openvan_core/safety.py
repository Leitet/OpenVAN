"""Safety layer.

Every intent — whether it came from the AI, a button, or an automation — passes
through the :class:`SafetyValidator` before it can act on hardware. Rules can
allow, deny, or modify an intent. The first rule to deny wins.

This is the "OpenVan verifies battery state, vehicle status, safety rules and
environmental constraints" promise from the vision, made concrete.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .intents import Intent

if TYPE_CHECKING:  # pragma: no cover
    from .hub import Hub


@dataclass
class SafetyDecision:
    allowed: bool
    reason: str = ""
    modified_params: dict[str, Any] | None = None


class SafetyRule(ABC):
    name: str = "rule"

    @abstractmethod
    async def evaluate(self, intent: Intent, hub: "Hub") -> SafetyDecision | None:
        """Return a decision, or ``None`` when the rule does not apply."""


class SafetyValidator:
    def __init__(self, rules: list[SafetyRule] | None = None) -> None:
        self.rules = rules or []

    async def check(self, intent: Intent, hub: "Hub") -> SafetyDecision:
        params = dict(intent.params)
        for rule in self.rules:
            decision = await rule.evaluate(intent, hub)
            if decision is None:
                continue
            if not decision.allowed:
                return decision
            if decision.modified_params is not None:
                params = decision.modified_params
        return SafetyDecision(allowed=True, modified_params=params)


class CriticalBatteryLoadShedding(SafetyRule):
    """Refuse to switch on non-essential loads when the house battery is critical.

    Physically defensible: below a critical state of charge you shed every
    non-essential load to protect the battery and preserve base systems. An
    entity opts in by setting ``attributes["essential"] = True``.
    """

    name = "critical_battery_load_shedding"

    def __init__(
        self,
        soc_entity: str = "sensor.house_battery_soc",
        critical_soc: float = 10.0,
    ) -> None:
        self.soc_entity = soc_entity
        self.critical_soc = critical_soc

    async def evaluate(self, intent: Intent, hub: "Hub") -> SafetyDecision | None:
        if intent.command != "turn_on":
            return None
        entity = hub.get_entity(intent.entity_id)
        if entity is None or entity.attributes.get("essential", False):
            return None
        soc = hub.get_entity(self.soc_entity)
        if soc is None or soc.state is None:
            return None
        try:
            level = float(soc.state)
        except (TypeError, ValueError):
            return None
        if level < self.critical_soc:
            return SafetyDecision(
                allowed=False,
                reason=(
                    f"Battery at {level:.0f}% is below the critical {self.critical_soc:.0f}% "
                    f"threshold — refusing to switch on non-essential '{entity.name}'."
                ),
            )
        return SafetyDecision(allowed=True)


class FuelRequiredToStart(SafetyRule):
    """Refuse to start a fuel-burning appliance without enough fuel.

    An entity opts in by declaring ``attributes["fuel_signal"]`` — the raw twin
    signal (0–100 %) holding its fuel level. Physically obvious: a diesel heater
    cannot run on an empty tank.
    """

    name = "fuel_required_to_start"

    def __init__(self, min_level: float = 5.0) -> None:
        self.min_level = min_level

    async def evaluate(self, intent: Intent, hub: "Hub") -> SafetyDecision | None:
        if intent.command != "turn_on":
            return None
        entity = hub.get_entity(intent.entity_id)
        if entity is None:
            return None
        fuel_signal = entity.attributes.get("fuel_signal")
        if not fuel_signal:
            return None
        level = hub.twin.get(fuel_signal)
        if level is None:
            return None
        try:
            level = float(level)
        except (TypeError, ValueError):
            return None
        if level < self.min_level:
            return SafetyDecision(
                allowed=False,
                reason=(
                    f"{entity.name}: fuel at {level:.0f}% is below the {self.min_level:.0f}% "
                    f"minimum — refusing to start."
                ),
            )
        return SafetyDecision(allowed=True)


class PumpDryRunProtection(SafetyRule):
    """Refuse to run a pump dry — running a water pump with no water damages it.

    An entity opts in with ``attributes["dry_run_signal"]`` — the raw twin signal
    (0–100 %) holding the level of the source tank it draws from.
    """

    name = "pump_dry_run_protection"

    def __init__(self, min_level: float = 2.0) -> None:
        self.min_level = min_level

    async def evaluate(self, intent: Intent, hub: "Hub") -> SafetyDecision | None:
        if intent.command != "turn_on":
            return None
        entity = hub.get_entity(intent.entity_id)
        if entity is None:
            return None
        signal = entity.attributes.get("dry_run_signal")
        if not signal:
            return None
        level = hub.twin.get(signal)
        if level is None:
            return None
        try:
            level = float(level)
        except (TypeError, ValueError):
            return None
        if level < self.min_level:
            return SafetyDecision(
                allowed=False,
                reason=(
                    f"{entity.name}: source tank at {level:.0f}% — refusing to run the "
                    f"pump dry."
                ),
            )
        return SafetyDecision(allowed=True)
