"""Intents — the boundary between the AI and the hardware.

An AI (local LLM, cloud LLM, or hybrid — OpenVan stays model-agnostic) never
touches hardware. It only proposes an :class:`Intent`. OpenVan Core then decides,
via the safety layer, whether that intent may run. This module also carries a
tiny rule-based :class:`IntentResolver` so text commands work fully offline; it
is a drop-in seam for an LLM-backed resolver.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Intent:
    entity_id: str
    command: str
    params: dict[str, Any] = field(default_factory=dict)
    source: str = "api"  # "voice" | "text" | "api" | "automation"
    raw_text: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "command": self.command,
            "params": dict(self.params),
            "source": self.source,
            "raw_text": self.raw_text,
        }


@dataclass
class IntentResult:
    ok: bool
    reason: str = ""
    blocked_by_safety: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "blocked_by_safety": self.blocked_by_safety,
        }


class IntentResolver:
    """Maps natural language to an :class:`Intent`.

    This is an intentionally small, offline, rule-based stub. Replace it with an
    LLM-backed resolver (local or cloud) without changing anything downstream:
    the resolver's only job is to *propose* an Intent — safety still decides.
    """

    _OFF_WORDS = ("off", "stop", "disable", "close", "shut")
    _ON_WORDS = ("on", "start", "enable", "open", "turn up")

    async def startup(self) -> None:
        """Hook for resolvers that need async initialisation (no-op here)."""

    async def resolve(self, text: str, entities: dict[str, Any]) -> Intent | None:
        lowered = text.lower()
        for entity in entities.values():
            if not entity.controllable:
                continue
            if entity.name.lower() not in lowered and entity.entity_id not in lowered:
                continue
            command = self._pick_command(lowered, entity.commands)
            if command:
                return Intent(
                    entity_id=entity.entity_id,
                    command=command,
                    source="text",
                    raw_text=text,
                )
        return None

    def _pick_command(self, lowered: str, commands: list[str]) -> str | None:
        if "turn_off" in commands and any(w in lowered for w in self._OFF_WORDS):
            return "turn_off"
        if "turn_on" in commands and any(w in lowered for w in self._ON_WORDS):
            return "turn_on"
        return commands[0] if commands else None
