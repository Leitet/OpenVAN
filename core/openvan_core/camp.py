"""Camp service — find places to spend the night near the van.

Discovers camp sources (packages under ``campsources/``), searches the enabled
ones around the van's GPS, then dedups, ranks by distance and caches the result.
Offline-first: with no location or no working source it serves the last cached
list; the ``sim`` source always returns something. The assistant proposes from
what this returns — it never navigates or acts on its own (read-only).
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from typing import Any, Callable

from .campsources import CampSource, CampSpot, discover_camp_sources, registered_camp_sources

logger = logging.getLogger(__name__)

Location = tuple[float | None, float | None]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


class CampService:
    def __init__(self, config: Any, get_location: Callable[[], Location]) -> None:
        self.config = config
        self.get_location = get_location
        self._sources: dict[str, CampSource] = {}
        self._cache: list[dict[str, Any]] = []

    # --- lifecycle -------------------------------------------------------
    def discover(self) -> None:
        discover_camp_sources(self.config.camp_sources_dir)
        for cls in registered_camp_sources():
            if cls.id not in self._sources:
                self._sources[cls.id] = cls()
        self._load_cache()
        logger.info("camp sources: %s", ", ".join(sorted(self._sources)) or "none")

    # --- source management ----------------------------------------------
    def enabled_ids(self) -> list[str]:
        return [s for s in self.config.camp_sources if s in self._sources]

    def source_infos(self) -> list[dict[str, Any]]:
        return [
            {
                "id": s.id,
                "name": s.name,
                "enabled": s.id in self.config.camp_sources,
                "requires_internet": s.requires_internet,
                "requires_key": s.requires_key,
            }
            for s in self._sources.values()
        ]

    def set_enabled(self, source_id: str, enabled: bool) -> bool:
        if source_id not in self._sources:
            return False
        current = list(self.config.camp_sources)
        if enabled and source_id not in current:
            current.append(source_id)
        elif not enabled and source_id in current:
            current.remove(source_id)
        self.config.camp_sources = current
        return True

    # --- search ----------------------------------------------------------
    async def search(
        self, radius_km: float | None = None, limit: int = 20
    ) -> dict[str, Any]:
        radius = float(radius_km or self.config.camp_search_radius_km)
        lat, lon = self.get_location()
        if lat is None or lon is None:
            return {"location": None, "radius_km": radius, "spots": self._cache}
        lat, lon = float(lat), float(lon)

        ids = self.enabled_ids()
        results = await asyncio.gather(
            *(self._safe_search(self._sources[sid], lat, lon, radius, limit) for sid in ids)
        )
        spots: list[CampSpot] = [s for sub in results for s in sub]
        for s in spots:
            s.distance_km = round(_haversine_km(lat, lon, s.lat, s.lon), 1)
        spots = [s for s in self._dedup(spots) if (s.distance_km or 0) <= radius]
        spots.sort(key=lambda s: s.distance_km if s.distance_km is not None else 1e9)
        spots = spots[:limit]

        payload = {
            "location": {"lat": lat, "lon": lon},
            "radius_km": radius,
            "sources": ids,
            "updated_at": time.time(),
            "spots": [s.as_dict() for s in spots],
        }
        if spots:
            self._cache = payload["spots"]
            self._save_cache()
        return payload

    async def _safe_search(
        self, source: CampSource, lat: float, lon: float, radius: float, limit: int
    ) -> list[CampSpot]:
        try:
            if not await source.available():
                return []
            return await source.search(lat, lon, radius, limit)
        except Exception as exc:  # a bad source must never break the search
            logger.warning("camp source %s failed: %r", source.id, exc)
            return []

    @staticmethod
    def _dedup(spots: list[CampSpot]) -> list[CampSpot]:
        """Merge near-identical spots from different sources (same ~100m cell),
        keeping the richer entry."""
        best: dict[tuple[float, float], CampSpot] = {}
        for s in spots:
            key = (round(s.lat, 3), round(s.lon, 3))
            cur = best.get(key)
            if cur is None or (s.rating or 0) > (cur.rating or 0) or len(s.amenities) > len(
                cur.amenities
            ):
                best[key] = s
        return list(best.values())

    # --- cache -----------------------------------------------------------
    def _cache_path(self):
        return self.config.data_dir / "camp.json"

    def _load_cache(self) -> None:
        path = self._cache_path()
        if not path.exists():
            return
        try:
            self._cache = json.loads(path.read_text())
        except (OSError, ValueError):
            logger.warning("could not read camp cache")

    def _save_cache(self) -> None:
        path = self._cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(json.dumps(self._cache))
        except OSError:
            logger.warning("could not write camp cache")
