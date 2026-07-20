"""Coverage memory — where the mobile signal was strong.

Connectivity is a van-life pain point you plan around: when the signal drops at a
stop, the useful question is *"was it better just back there?"*. This service quietly
records ``(gps, signal)`` samples as the van moves, so the :class:`WeakSignal` advisor
can point back to the nearest recent strong-coverage spot ("you had 85% about 300 m
north of here").

It's deterministic and offline-first — a bounded in-memory trail keyed to GPS, fed by
``twin.signal_changed``. No history file, no cloud; it simply remembers the road you
just drove. A stateful trail like this doesn't fit the stateless threshold-advisor
model, so it lives here as a tiny service the advisor reads.
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from .camp import _haversine_km
from .events import Event, EventBus

if TYPE_CHECKING:  # pragma: no cover
    from .twin import VanTwin

_COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2, degrees clockwise from north."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def compass_point(bearing_deg: float) -> str:
    """Bearing → an 8-point compass word ('north-east')."""
    return _COMPASS[round(bearing_deg / 45.0) % 8]


@dataclass(frozen=True)
class CoverageSpot:
    lat: float
    lon: float
    signal_pct: float
    ts: float = 0.0  # wall-clock when recorded (age-capped in best_nearby)


@dataclass(frozen=True)
class NearbyCoverage:
    spot: CoverageSpot
    distance_m: float
    direction: str  # compass word from the current position toward the spot


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


class CoverageMemory:
    """A bounded trail of where the signal was, keyed to GPS."""

    def __init__(
        self,
        bus: EventBus,
        twin: "VanTwin",
        *,
        good_pct: float = 50.0,
        min_move_m: float = 40.0,
        max_samples: int = 400,
        max_age_s: float = 6 * 3600.0,
    ) -> None:
        self.bus = bus
        self.twin = twin
        self.good_pct = good_pct
        self.min_move_m = min_move_m
        self.max_age_s = max_age_s
        self._samples: deque[CoverageSpot] = deque(maxlen=max_samples)
        self._unsub: Callable[[], None] | None = None

    def start(self) -> None:
        if self._unsub is None:
            self._unsub = self.bus.subscribe("twin.signal_changed", self._on_change)

    def stop(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    async def _on_change(self, event: Event) -> None:
        key = event.data.get("key")
        if key in ("gps.lat", "gps.lon", "connectivity.signal_pct", "connectivity.online"):
            self.record()

    def record(self) -> None:
        """Snapshot the current position + signal, if we've moved far enough to make
        it a distinct spot (so a parked van doesn't flood the trail)."""
        lat = _as_float(self.twin.get("gps.lat"))
        lon = _as_float(self.twin.get("gps.lon"))
        if lat is None or lon is None:
            return
        # Explicitly offline → a real 0% dead-zone worth remembering. Otherwise only
        # record a *known* signal — never invent 0% from a missing reading, which
        # would pollute the trail with false dead-zones.
        online = self.twin.get("connectivity.online")
        sig = _as_float(self.twin.get("connectivity.signal_pct"))
        if online is False:
            signal = 0.0
        elif sig is not None:
            signal = sig
        else:
            return
        if self._samples:
            last = self._samples[-1]
            if _haversine_km(last.lat, last.lon, lat, lon) * 1000.0 < self.min_move_m:
                # Same place — keep the better reading of the two.
                if signal > last.signal_pct:
                    self._samples[-1] = CoverageSpot(last.lat, last.lon, signal, time.time())
                return
        self._samples.append(CoverageSpot(lat, lon, signal, time.time()))

    def best_nearby(
        self, lat: float, lon: float, *, within_km: float = 2.0, better_than: float = 0.0
    ) -> NearbyCoverage | None:
        """The closest recorded spot that had *strong* signal (≥ ``good_pct``), is a
        meaningful distance from here (not this very spot), within ``within_km``, and
        beats the current reading. ``None`` if there's nowhere better to point to."""
        best: NearbyCoverage | None = None
        threshold = max(self.good_pct, better_than + 10.0)  # clearly better, not marginal
        now = time.time()
        for spot in self._samples:
            if spot.signal_pct < threshold:
                continue
            # A spot from hours ago isn't "just back there" — age-cap the trail.
            if spot.ts and now - spot.ts > self.max_age_s:
                continue
            dist_m = _haversine_km(lat, lon, spot.lat, spot.lon) * 1000.0
            if dist_m < self.min_move_m or dist_m > within_km * 1000.0:
                continue
            if best is None or dist_m < best.distance_m:
                best = NearbyCoverage(spot, dist_m, compass_point(_bearing_deg(lat, lon, spot.lat, spot.lon)))
        return best
