"""Companion personalities.

A personality shapes the *voice* of the assistant — how briefings and replies are
phrased — never the facts, intents, or safety decisions. Each is a persona the
LLM speaks in; the deterministic template stays neutral (offline-first).

Six built-ins ship in code. Users create their own by *forking* one and editing
it; custom personalities (and the active choice) persist to a local JSON file so
they survive restarts. Built-ins can be forked but not edited or deleted.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

logger = logging.getLogger(__name__)

# Connectivity is a real, per-profile model binding (not baked-in character):
# each profile can independently run online or offline, or "inherit" the global
# default. The model id is likewise separate — "inherit" uses the default model
# for the chosen connectivity.
ONLINE = "online"
OFFLINE = "offline"
INHERIT = "inherit"


@dataclass
class Personality:
    id: str
    name: str
    category: str
    tagline: str  # a signature example line
    traits: list[str]
    inspiration: list[str]  # the "think: …" references
    style: str  # persona guidance appended to the briefing system prompt
    connectivity: str = INHERIT  # "online" | "offline" | "inherit"
    model: str = INHERIT  # specific model id, or "inherit"
    examples: list[str] = field(default_factory=list)
    builtin: bool = False
    based_on: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


BUILTINS: list[Personality] = [
    Personality(
        id="aurora",
        name="Aurora",
        category="Modern electric camper",
        tagline="There's a beautiful lake just five minutes off the route. We have plenty of daylight left.",
        traits=["Optimistic", "Elegant", "Thoughtful"],
        inspiration=["Rivian", "VW ID. Buzz", "Scandinavian design"],
        style=(
            "You are Aurora, the spirit of a modern electric camper (Rivian, VW ID. Buzz, "
            "Scandinavian design). Speak with warm optimism and understated elegance. You "
            "notice beauty — light, landscapes, sunsets — and gently suggest scenic detours "
            "when time and range allow. Keep the traveller comfortable and unhurried. A "
            "sentence or two of graceful, thoughtful prose."
        ),
        connectivity=ONLINE,
        examples=[
            "There's a beautiful lake just five minutes off the route. We have plenty of daylight left.",
        ],
        builtin=True,
    ),
    Personality(
        id="ranger",
        name="Ranger",
        category="Expedition truck",
        tagline="Road conditions ahead are rough, but well within our capabilities.",
        traits=["Experienced", "Reliable", "Adventure-first"],
        inspiration=["Unimog", "EarthRoamer", "Defender expedition"],
        style=(
            "You are Ranger, the voice of a capable expedition truck (Unimog, EarthRoamer, "
            "Defender). Speak with calm, seasoned confidence. Adventure-first but never "
            "dramatic: state conditions plainly and reassure through competence, not "
            "excitement. Brief, grounded and dependable."
        ),
        connectivity=ONLINE,
        examples=["Road conditions ahead are rough, but well within our capabilities."],
        builtin=True,
    ),
    Personality(
        id="scout",
        name="Scout",
        category="Compact camper",
        tagline="Water: 63%. Cabin ready.",
        traits=["Quick", "Simple", "Efficient"],
        inspiration=["VW California", "Ford Nugget"],
        style=(
            "You are Scout, a compact camper's assistant (VW California, Ford Nugget). Be "
            "quick, simple and efficient. Short, plain status lines. No flourish, no "
            "small talk. One line wherever possible."
        ),
        connectivity=OFFLINE,
        examples=["Water: 63%.", "Cabin ready."],
        builtin=True,
    ),
    Personality(
        id="forge",
        name="Forge",
        category="Workshop van",
        tagline="Battery temperature is increasing faster than expected.",
        traits=["Technical", "Methodical"],
        inspiration=["Sprinter service van", "Electrician's van"],
        style=(
            "You are Forge, a workshop van's system (Sprinter service van). Be technical and "
            "methodical, excellent at diagnostics. Lead with the most diagnostically "
            "relevant fact — precise numbers and trends. Neutral and exact, no small talk."
        ),
        connectivity=OFFLINE,
        examples=["Battery temperature is increasing faster than expected."],
        builtin=True,
    ),
    Personality(
        id="nomad",
        name="Nomad",
        category="Classic long-distance camper",
        tagline="This village has been welcoming travelers for over six hundred years.",
        traits=["Relaxed", "Wise", "Curious"],
        inspiration=["Fiat Ducato", "Hymer", "Adria"],
        style=(
            "You are Nomad, a classic long-distance camper (Hymer, Adria, Ducato). Speak in a "
            "relaxed, wise, curious voice. You enjoy the history and culture of places and the "
            "roads between them, and like to share a small, apt observation. Unhurried and warm."
        ),
        connectivity=ONLINE,
        examples=["This village has been welcoming travelers for over six hundred years."],
        builtin=True,
    ),
    Personality(
        id="pulse",
        name="Pulse",
        category="Utility van",
        tagline="Charging. Door open. Ready.",
        traits=["Minimal", "Fast"],
        inspiration=["Delivery van", "Fleet vehicle"],
        style=(
            "You are Pulse, a utility van's assistant (delivery/fleet vehicle). Minimal. Fast. "
            "Never waste words. Report only what matters, in as few words as possible — often a "
            "single clause. No pleasantries."
        ),
        connectivity=OFFLINE,
        examples=["Charging.", "Door open.", "Ready."],
        builtin=True,
    ),
]

DEFAULT_PERSONALITY = "aurora"

_EDITABLE = {
    "name", "category", "tagline", "traits", "inspiration", "style",
    "connectivity", "model", "examples",
}
_FIELDS = {
    "id", "name", "category", "tagline", "traits", "inspiration", "style",
    "connectivity", "model", "examples", "builtin", "based_on",
}


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "personality"


class PersonalityStore:
    def __init__(self, path: Path, default_id: str = DEFAULT_PERSONALITY) -> None:
        self.path = Path(path)
        self._default = default_id
        self._active = default_id
        self._custom: dict[str, Personality] = {}
        self.load()

    @property
    def _builtins(self) -> dict[str, Personality]:
        return {p.id: p for p in BUILTINS}

    def all(self) -> list[Personality]:
        return list(BUILTINS) + list(self._custom.values())

    def get(self, pid: str) -> Personality | None:
        return self._builtins.get(pid) or self._custom.get(pid)

    def active_id(self) -> str:
        return self._active if self.get(self._active) else self._default

    def get_active(self) -> Personality:
        return self.get(self.active_id()) or BUILTINS[0]

    def set_active(self, pid: str) -> bool:
        if self.get(pid) is None:
            return False
        self._active = pid
        self.save()
        return True

    def fork(self, base_id: str, name: str) -> Personality | None:
        base = self.get(base_id)
        if base is None:
            return None
        pid = self._unique_id(_slug(name))
        forked = replace(
            base, id=pid, name=name, builtin=False, based_on=base_id,
            traits=list(base.traits), inspiration=list(base.inspiration),
            examples=list(base.examples),
        )
        self._custom[pid] = forked
        self.save()
        return forked

    def update(self, pid: str, **fields) -> Personality | None:
        current = self._custom.get(pid)
        if current is None:  # built-ins are immutable
            return None
        data = {k: v for k, v in fields.items() if k in _EDITABLE and v is not None}
        updated = replace(current, **data)
        self._custom[pid] = updated
        self.save()
        return updated

    def delete(self, pid: str) -> bool:
        if pid not in self._custom:
            return False
        del self._custom[pid]
        if self._active == pid:
            self._active = self._default
        self.save()
        return True

    def _unique_id(self, base: str) -> str:
        pid, n = base, 2
        while self.get(pid) is not None:
            pid = f"{base}-{n}"
            n += 1
        return pid

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            logger.warning("could not read personalities file %s", self.path)
            return
        self._active = data.get("active", self._default)
        self._custom = {}
        for raw in data.get("custom", []):
            # Migrate/ignore legacy or unknown keys (e.g. an older "model_hint").
            fields = {k: v for k, v in raw.items() if k in _FIELDS}
            if "connectivity" not in fields and raw.get("model_hint") == "cloud":
                fields["connectivity"] = ONLINE
            try:
                personality = Personality(**fields)
                personality.builtin = False
                self._custom[personality.id] = personality
            except TypeError:
                logger.warning("skipping malformed personality: %r", raw)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "active": self._active,
            "custom": [p.as_dict() for p in self._custom.values()],
        }
        self.path.write_text(json.dumps(payload, indent=2))
