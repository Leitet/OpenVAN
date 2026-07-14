"""Entities — OpenVan's semantic model of the van.

Where the twin holds raw signals (``house_battery.soc = 82``), entities are the
meaningful, UI- and AI-facing objects (``sensor.house_battery_soc`` with a unit,
a friendly name and a category). This mirrors Home Assistant deliberately:
OpenVan extends Home Assistant rather than replacing it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Entity:
    entity_id: str  # "<domain>.<object_id>", e.g. "light.cabin"
    name: str
    domain: str  # "sensor", "light", "climate", "water", "switch", ...
    category: str  # human grouping: "energy", "lighting", "climate", "water"
    state: Any = None
    unit: str | None = None
    controllable: bool = False
    commands: list[str] = field(default_factory=list)  # e.g. ["turn_on", "turn_off"]
    attributes: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "domain": self.domain,
            "category": self.category,
            "state": self.state,
            "unit": self.unit,
            "controllable": self.controllable,
            "commands": list(self.commands),
            "attributes": dict(self.attributes),
        }
