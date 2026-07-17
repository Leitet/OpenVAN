"""The Hub ties Core together.

It owns the entity registry, routes commands to plugin handlers, and — crucially
— funnels every intent through the safety validator before anything acts on
hardware. Plugins register entities (with an optional command handler) here.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from .entities import Entity
from .events import EventBus
from .intents import Intent, IntentResolver, IntentResult
from .safety import SafetyValidator
from .twin import VanTwin

# A command handler receives (command, params) and drives the actuator.
CommandHandler = Callable[[str, dict[str, Any]], Awaitable[None]]


class Hub:
    def __init__(
        self,
        bus: EventBus,
        twin: VanTwin,
        safety: SafetyValidator,
        resolver: IntentResolver | None = None,
    ) -> None:
        self.bus = bus
        self.twin = twin
        self.safety = safety
        self.resolver = resolver or IntentResolver()
        self.entities: dict[str, Entity] = {}
        self._handlers: dict[str, CommandHandler] = {}

    # --- entity registry -------------------------------------------------
    async def register_entity(
        self, entity: Entity, handler: CommandHandler | None = None
    ) -> None:
        self.entities[entity.entity_id] = entity
        if handler is not None:
            self._handlers[entity.entity_id] = handler
        await self.bus.publish("entity.registered", {"entity": entity.as_dict()})

    def get_entity(self, entity_id: str) -> Entity | None:
        return self.entities.get(entity_id)

    async def remove_entity(self, entity_id: str) -> bool:
        """Drop an entity (and its handler) and tell subscribers, so a removed
        device disappears from the UI. Used for dynamic devices like cameras."""
        if entity_id not in self.entities:
            return False
        self.entities.pop(entity_id, None)
        self._handlers.pop(entity_id, None)
        await self.bus.publish("entity.removed", {"entity_id": entity_id})
        return True

    async def set_state(
        self, entity_id: str, state: Any, attributes: dict[str, Any] | None = None
    ) -> None:
        entity = self.entities.get(entity_id)
        if entity is None:
            raise KeyError(f"unknown entity '{entity_id}'")
        entity.state = state
        if attributes:
            entity.attributes.update(attributes)
        await self.bus.publish("entity.state_changed", {"entity": entity.as_dict()})

    # --- intent execution ------------------------------------------------
    async def execute_intent(self, intent: Intent) -> IntentResult:
        entity = self.entities.get(intent.entity_id)
        if entity is None:
            return IntentResult(False, f"Unknown entity '{intent.entity_id}'")
        if not entity.controllable or intent.command not in entity.commands:
            return IntentResult(
                False, f"'{intent.command}' is not supported by {intent.entity_id}"
            )

        decision = await self.safety.check(intent, self)
        await self.bus.publish(
            "intent.evaluated",
            {
                "intent": intent.as_dict(),
                "allowed": decision.allowed,
                "reason": decision.reason,
            },
        )
        if not decision.allowed:
            return IntentResult(False, decision.reason, blocked_by_safety=True)

        handler = self._handlers.get(intent.entity_id)
        if handler is None:
            return IntentResult(False, f"No handler for {intent.entity_id}")

        params = decision.modified_params if decision.modified_params is not None else intent.params
        await handler(intent.command, params)
        return IntentResult(True, decision.reason or "ok")

    async def execute_text(self, text: str) -> IntentResult:
        intent = await self.resolver.resolve(text, self.entities)
        if intent is None:
            return IntentResult(False, f"Could not understand: '{text}'")
        return await self.execute_intent(intent)
