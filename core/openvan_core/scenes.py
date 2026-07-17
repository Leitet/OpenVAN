"""Scenes — one tap (or one word) for a whole routine.

The daily rhythm of van life is repetitive: every night you turn the lights off,
drop the heater to a sleeping temperature and kill the pump; every morning you
bring it back; when you leave you switch everything off. A scene bundles those
into a single named routine so "goodnight" does it all — by button or by voice.

A scene is just an ordered list of the same **intents** the assistant would
propose, so every step still passes through the safety layer (Rule 2): a scene can
never do anything a direct command couldn't. Offline-first and model-free — scenes
are deterministic bundles; the model is only used, elsewhere, to *recognise* the
phrase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .intents import Intent

if TYPE_CHECKING:  # pragma: no cover
    from .hub import Hub


@dataclass
class SceneStep:
    entity_id: str
    command: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Scene:
    id: str
    name: str
    icon: str  # UI hint: "moon" | "sun" | "door" | "tent"
    description: str
    steps: list[SceneStep]

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "icon": self.icon, "description": self.description}


def default_scenes(sleep_c: float = 16.0, comfort_c: float = 20.0) -> list[Scene]:
    """The four everyday routines. Heater setpoints default to a cosy sleep/comfort
    pair but are configurable (Config tuning) — nothing hardcoded."""
    return [
        Scene(
            "goodnight", "Goodnight", "moon",
            "Lights off, heater to a cosy sleeping temperature, pump off.",
            [
                SceneStep("light.cabin", "turn_off"),
                SceneStep("climate.diesel_heater", "set_temperature", {"temperature": sleep_c}),
                SceneStep("climate.diesel_heater", "turn_on"),
                SceneStep("switch.water_pump", "turn_off"),
            ],
        ),
        Scene(
            "morning", "Good morning", "sun",
            "Lights on and warm the cabin back up.",
            [
                SceneStep("light.cabin", "turn_on"),
                SceneStep("climate.diesel_heater", "set_temperature", {"temperature": comfort_c}),
                SceneStep("climate.diesel_heater", "turn_on"),
            ],
        ),
        Scene(
            "setup_camp", "Set up camp", "tent",
            "Arriving: lights on, comfortable warmth.",
            [
                SceneStep("light.cabin", "turn_on"),
                SceneStep("climate.diesel_heater", "set_temperature", {"temperature": comfort_c}),
                SceneStep("climate.diesel_heater", "turn_on"),
            ],
        ),
        Scene(
            "leaving", "Leaving", "door",
            "Everything off before you drive away.",
            [
                SceneStep("light.cabin", "turn_off"),
                SceneStep("climate.diesel_heater", "turn_off"),
                SceneStep("switch.water_pump", "turn_off"),
            ],
        ),
    ]


class SceneEngine:
    def __init__(self, hub: "Hub", scenes: list[Scene] | None = None) -> None:
        self.hub = hub
        self._scenes = {s.id: s for s in (scenes if scenes is not None else default_scenes())}

    def list(self) -> list[dict[str, Any]]:
        return [s.as_dict() for s in self._scenes.values()]

    def get(self, scene_id: str) -> Scene | None:
        return self._scenes.get(scene_id)

    async def run(self, scene_id: str) -> dict[str, Any] | None:
        """Run every step through the safety-checked intent path. Steps whose
        entity isn't present are skipped (a plugin may be absent); a step blocked by
        safety is reported but doesn't abort the rest."""
        scene = self._scenes.get(scene_id)
        if scene is None:
            return None
        results: list[dict[str, Any]] = []
        for step in scene.steps:
            if step.entity_id not in self.hub.entities:
                results.append(
                    {"entity_id": step.entity_id, "command": step.command,
                     "ok": False, "skipped": True, "reason": "not present"}
                )
                continue
            res = await self.hub.execute_intent(
                Intent(step.entity_id, step.command, dict(step.params), source="scene")
            )
            results.append(
                {"entity_id": step.entity_id, "command": step.command,
                 "ok": res.ok, "reason": res.reason,
                 "blocked_by_safety": res.blocked_by_safety}
            )
        applied = sum(1 for r in results if r.get("ok"))
        return {
            "scene": scene.as_dict(),
            "steps": results,
            "applied": applied,
            "ok": applied > 0,
        }
