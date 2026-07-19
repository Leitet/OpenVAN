"""Trip ledger — a simple journey stats-book.

Van-lifers love knowing "this trip": how far, how many nights, where, how much sun.
This composes those from data OpenVan already keeps — the vehicle odometer, the
travel journal (`memory.py`) and the telemetry time-series — so nothing new needs
recording. A trip is just a **start marker** (odometer + timestamp) you can reset;
everything is measured relative to it.

Wall-clock throughout (`time.time()`), matching how the journal and telemetry stamp
their rows — so distance, nights and solar Wh all line up on one timebase. Offline
and local: the marker lives in the config store, no cloud.
"""

from __future__ import annotations

import time
from typing import Any


def _f(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


class TripLedger:
    NS = "trip"

    def __init__(self, store: Any, twin: Any, memory: Any = None, telemetry: Any = None) -> None:
        self.store = store
        self.twin = twin
        self.memory = memory
        self.telemetry = telemetry

    def _odometer(self) -> float:
        return _f(self.twin.get("vehicle.odometer_km"))

    def load(self) -> None:
        """Ensure a start marker exists — first run pins it to the current state."""
        if self.store is not None and self.store.get(self.NS, "start") is None:
            self.reset()

    def reset(self, now: float | None = None) -> dict[str, Any]:
        """Start a fresh trip from here."""
        start = {"epoch": now if now is not None else time.time(), "odometer_km": self._odometer()}
        if self.store is not None:
            self.store.set_many(self.NS, {"start": start})
        return start

    def stats(self, now: float | None = None) -> dict[str, Any]:
        now = now if now is not None else time.time()
        start = (self.store.get(self.NS, "start") if self.store is not None else None) or {}
        start_epoch = start.get("epoch")
        start_odo = _f(start.get("odometer_km"))

        distance_km = max(0.0, self._odometer() - start_odo)
        days = max(0.0, (now - start_epoch) / 86400.0) if start_epoch else 0.0

        # Nights + places from the journal (stays opened since the trip began).
        stays = []
        if self.memory is not None:
            stays = [
                s for s in self.memory.list_stays(500)
                if s.get("started_at") and s["started_at"] >= (start_epoch or 0.0)
            ]
        places = sorted({s["place"] for s in stays if s.get("place")})

        # Solar harvested (Wh) — the integral of PV power over the trip.
        solar_wh = None
        if self.telemetry is not None and start_epoch:
            solar_wh = round(self.telemetry.integral("solar.power", start_epoch, now) / 3600.0, 0)

        return {
            "started_at": start_epoch,
            "days": round(days, 2),
            "distance_km": round(distance_km, 1),
            "nights": len(stays),
            "places": places,
            "place_count": len(places),
            "solar_wh": solar_wh,
        }
