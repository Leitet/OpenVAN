"""Road network — make the simulated van follow *real* roads.

The environment simulation dead-reckons the van from speed + heading, which draws
straight lines across the map. This service snaps that motion onto the actual road
graph so the GPS trace follows real streets — the same roads you see on the
OpenStreetMap tiles in the product UI.

It fetches nearby drivable ways from **Overpass** (keyless, like the weather and
camp sources), builds a little graph of connected segments, and advances the van
along it. At a junction it picks the outgoing road whose bearing best matches the
driver's heading — so turning the wheel in the Turbo Dash still chooses where you
go, you just can't drive through buildings any more.

Offline-first (Rule 3): fetching is best-effort and happens in the background. Until
a graph is loaded — or when Overpass is unreachable — :meth:`advance` returns
``None`` and the caller falls back to free dead-reckoning. So the sim never blocks
and never *requires* the network; roads are an enhancement.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_HEADERS = {"User-Agent": "OpenVan/0.1 (camper-van assistant)", "Accept": "application/json"}
# Drivable highway classes — skip footways, cycleways, tracks, etc.
_DRIVABLE = (
    "motorway|trunk|primary|secondary|tertiary|unclassified|residential|"
    "living_street|service|road|motorway_link|trunk_link|primary_link|"
    "secondary_link|tertiary_link"
)


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi = math.radians(b[0] - a[0])
    dlmb = math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def _bearing(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Compass bearing a→b in degrees (0 = north, 90 = east)."""
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlon = math.radians(b[1] - a[1])
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _angle_diff(a: float, b: float) -> float:
    d = abs((a - b) % 360.0)
    return min(d, 360.0 - d)


def _interp(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _parse_limit(value: Any) -> float | None:
    """OSM maxheight/maxweight → a float (metres / tonnes). Takes the leading number
    (handles "3.5", "3.5 m", "7.5 t"); returns None for feet/inches or unparseable."""
    if value is None:
        return None
    m = re.match(r"\s*([0-9]+(?:\.[0-9]+)?)", str(value))
    if not m or "'" in str(value) or '"' in str(value):
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


class RoadNetwork:
    """A local drivable-road graph plus a moving position along it."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.nodes: dict[int, tuple[float, float]] = {}
        self.adj: dict[int, set[int]] = defaultdict(set)
        # Height/weight limits per undirected segment (min-id, max-id) → {mh, mw}.
        self._seg_limits: dict[tuple[int, int], dict[str, float | None]] = {}
        # Where the loaded graph is centred, and how far it reaches (metres).
        self._center: tuple[float, float] | None = None
        self._radius_m = float(getattr(config, "roads_radius_m", 1600))
        # Driving state: we're on segment prev→cur, `progress_m` from prev.
        self._prev: int | None = None
        self._cur: int | None = None
        self._progress_m = 0.0
        self._fetching = False

    # --- loading ---------------------------------------------------------
    def loaded(self) -> bool:
        return bool(self.nodes)

    def covers(self, lat: float, lon: float) -> bool:
        """Is (lat, lon) comfortably inside the loaded graph? Re-fetch before we
        reach the edge so there's always road ahead."""
        if self._center is None:
            return False
        return _haversine_m(self._center, (lat, lon)) < self._radius_m * 0.6

    def ensure_coverage(self, lat: float, lon: float) -> None:
        """Kick off a background fetch if we're near/over the edge of coverage."""
        if self._fetching or self.covers(lat, lon):
            return
        self._fetching = True
        try:
            asyncio.get_running_loop().create_task(self._load(lat, lon))
        except RuntimeError:  # no loop (e.g. sync test) — skip, stay unloaded
            self._fetching = False

    def _cache_path(self) -> Path:
        return self.config.data_dir / "roads.json"

    def load_cache(self) -> None:
        path = self._cache_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            self._ingest(data.get("elements", []))
            c = data.get("center")
            if c:
                self._center = (c[0], c[1])
        except (OSError, ValueError, KeyError):
            logger.warning("could not read road cache")

    async def _load(self, lat: float, lon: float) -> None:
        try:
            radius = int(self._radius_m)
            query = (
                f"[out:json][timeout:20];"
                f'way["highway"~"^({_DRIVABLE})$"](around:{radius},{lat},{lon});'
                f"out geom;"
            )
            async with httpx.AsyncClient(timeout=httpx.Timeout(22.0, connect=5.0)) as client:
                resp = await client.post(_OVERPASS_URL, data={"data": query}, headers=_HEADERS)
                resp.raise_for_status()
                data = resp.json()
            elements = data.get("elements", [])
            self._ingest(elements)
            self._center = (lat, lon)
            self._save_cache(elements, lat, lon)
            logger.info("road graph loaded: %d nodes near %.4f,%.4f", len(self.nodes), lat, lon)
        except Exception as exc:  # unreachable / bad data → stay on dead reckoning
            logger.warning("road fetch failed: %r", exc)
        finally:
            self._fetching = False

    def _ingest(self, elements: list[dict]) -> None:
        """Build the node/adjacency graph from Overpass `out geom` ways."""
        for el in elements:
            if el.get("type") != "way":
                continue
            ids = el.get("nodes") or []
            geom = el.get("geometry") or []
            if len(ids) != len(geom) or len(ids) < 2:
                continue
            for i in range(len(ids)):
                self.nodes[ids[i]] = (geom[i]["lat"], geom[i]["lon"])
            tags = el.get("tags") or {}
            mh = _parse_limit(tags.get("maxheight"))
            mw = _parse_limit(tags.get("maxweight"))
            for i in range(len(ids) - 1):
                a, b = ids[i], ids[i + 1]
                self.adj[a].add(b)
                self.adj[b].add(a)
                if mh is not None or mw is not None:
                    self._seg_limits[(min(a, b), max(a, b))] = {"maxheight": mh, "maxweight": mw}

    def restriction_ahead(self, lookahead: int = 8) -> dict[str, float | None]:
        """Tightest height/weight limit on the current road and the next few segments
        (following the straightest continuation), so a warning fires *before* the
        van reaches a low bridge. Empty when no data is loaded."""
        prev, cur = self._prev, self._cur
        heights: list[float] = []
        weights: list[float] = []
        for _ in range(lookahead):
            if prev is None or cur is None:
                break
            lim = self._seg_limits.get((min(prev, cur), max(prev, cur)))
            if lim:
                if lim.get("maxheight") is not None:
                    heights.append(lim["maxheight"])
                if lim.get("maxweight") is not None:
                    weights.append(lim["maxweight"])
            nxt = [n for n in self.adj.get(cur, ()) if n != prev]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
        return {
            "maxheight": min(heights) if heights else None,
            "maxweight": min(weights) if weights else None,
        }

    def _save_cache(self, elements: list[dict], lat: float, lon: float) -> None:
        try:
            path = self._cache_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"center": [lat, lon], "elements": elements}))
        except OSError:
            logger.warning("could not write road cache")

    # --- driving ---------------------------------------------------------
    def _nearest_node(self, lat: float, lon: float) -> int | None:
        p = (lat, lon)
        best, best_d = None, float("inf")
        for nid, coord in self.nodes.items():
            d = _haversine_m(coord, p)
            if d < best_d:
                best, best_d = nid, d
        return best

    def _snap(self, lat: float, lon: float, heading: float) -> bool:
        """Latch onto the road nearest (lat, lon), heading along the branch that
        best matches the driver's heading. Returns False if there's no graph."""
        start = self._nearest_node(lat, lon)
        if start is None or not self.adj.get(start):
            return False
        nxt = min(
            self.adj[start],
            key=lambda n: _angle_diff(_bearing(self.nodes[start], self.nodes[n]), heading),
        )
        self._prev, self._cur, self._progress_m = start, nxt, 0.0
        return True

    def advance(
        self, lat: float, lon: float, heading: float, dist_m: float
    ) -> tuple[float, float, float] | None:
        """Move ``dist_m`` along the road graph from the current position, choosing
        junctions by ``heading``. Returns the new ``(lat, lon, heading)`` snapped to
        the road, or ``None`` if no graph is loaded (caller dead-reckons instead)."""
        self.ensure_coverage(lat, lon)
        if not self.loaded():
            return None
        # (Re)latch if we have no segment, lost a node, or drifted far from the road
        # (e.g. a bookmark/teleport set gps directly).
        drifted = (
            self._cur is None
            or self._prev is None
            or self._prev not in self.nodes
            or self._cur not in self.nodes
            or _haversine_m((lat, lon), self.nodes[self._prev]) > self._radius_m
        )
        if drifted and not self._snap(lat, lon, heading):
            return None

        remaining = max(0.0, dist_m)
        guard = 0
        while remaining > 0 and guard < 2000:
            guard += 1
            a, b = self.nodes[self._prev], self.nodes[self._cur]
            seg_len = _haversine_m(a, b)
            if seg_len <= 0.01:  # degenerate; hop to next
                self._advance_node(heading)
                continue
            if self._progress_m + remaining < seg_len:
                self._progress_m += remaining
                remaining = 0.0
            else:
                remaining -= seg_len - self._progress_m
                self._advance_node(heading)

        a, b = self.nodes[self._prev], self.nodes[self._cur]
        seg_len = max(0.01, _haversine_m(a, b))
        pos = _interp(a, b, min(1.0, self._progress_m / seg_len))
        new_heading = _bearing(a, b)
        return (round(pos[0], 6), round(pos[1], 6), round(new_heading, 1))

    def _advance_node(self, heading: float) -> None:
        """We reached ``self._cur``; pick the next node by heading and step onto it."""
        cur = self._cur
        assert cur is not None
        options = [n for n in self.adj[cur] if n != self._prev]
        if not options:  # dead end → U-turn
            options = list(self.adj[cur])
        cur_pos = self.nodes[cur]
        nxt = min(options, key=lambda n: _angle_diff(_bearing(cur_pos, self.nodes[n]), heading))
        self._prev, self._cur, self._progress_m = cur, nxt, 0.0
