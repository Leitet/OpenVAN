"""Camp-source system.

A *camp source* is an external provider of places to spend the night — campsites,
aires, wild spots — like Park4Night, iOverlander or OpenStreetMap. It is the
non-hardware sibling of the plugin system: sources live in packages under
``campsources/`` and self-register, so a user adds a new site the same way she
adds a water heater. Sources return :class:`CampSpot`s; :class:`camp.CampService`
aggregates the enabled ones near the van and the assistant proposes from them.

Hardware plugins bind to a ``Backend`` and register entities; a camp source is a
pure data provider, so it gets its own small base rather than being forced into
the entity model — but the shape (drop a package in a folder, self-register) is
the same. Offline-first (Rule 3): the ``sim`` source always works (Rule 1:
bench/tests) and cloud sources are an enhancement with a cached fallback.
"""

from __future__ import annotations

import importlib
import logging
import sys
from abc import ABC
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_REGISTRY: list[type["CampSource"]] = []


def registered_camp_sources() -> list[type["CampSource"]]:
    return list(_REGISTRY)


def clear_camp_registry() -> None:
    """Test helper — the registry is process-global."""
    _REGISTRY.clear()


@dataclass
class CampSpot:
    """One place to camp, from some source. ``distance_km`` is filled by the
    service relative to the query point."""

    source: str  # source id, e.g. "sim" | "overpass"
    source_id: str  # native id within that source
    name: str
    lat: float
    lon: float
    kind: str = "unknown"  # "campsite" | "aire" | "wild" | "parking"
    amenities: list[str] = field(default_factory=list)  # ["water","toilets","power",…]
    rating: float | None = None
    price: str | None = None
    description: str | None = None
    url: str | None = None
    distance_km: float | None = None

    @property
    def id(self) -> str:
        return f"{self.source}:{self.source_id}"

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["id"] = self.id
        return data


class CampSource(ABC):
    """A provider of camp spots. Subclass, set ``id`` + ``name``, implement
    ``search``. Self-registers on import (like :class:`~openvan_core.plugins.Plugin`)."""

    id: str = ""
    name: str = ""
    requires_internet: bool = False
    requires_key: bool = False
    # Editable settings this source needs, e.g. an API key or endpoint. Rendered in
    # the Admin UI and stored in the config database (never env vars). Each field:
    # {"key": str, "label": str, "secret": bool}.
    config_fields: list[dict[str, Any]] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if getattr(cls, "id", ""):
            _REGISTRY.append(cls)

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    async def available(self) -> bool:
        """Whether the source can run right now (has a key / network). Defaults to
        True; search should still fail gracefully (return [])."""
        return True

    async def search(
        self, lat: float, lon: float, radius_km: float, limit: int = 20
    ) -> list[CampSpot]:
        raise NotImplementedError


def discover_camp_sources(sources_dir: Path | str) -> None:
    """Import every package under ``sources_dir`` so its CampSource subclass
    registers (mirrors ``PluginManager.discover``)."""
    sources_dir = Path(sources_dir)
    if not sources_dir.is_dir():
        logger.warning("camp sources directory %s does not exist", sources_dir)
        return
    if str(sources_dir) not in sys.path:
        sys.path.insert(0, str(sources_dir))
    for child in sorted(sources_dir.iterdir()):
        if child.is_dir() and (child / "__init__.py").exists():
            logger.info("loading camp source package: %s", child.name)
            importlib.import_module(child.name)
