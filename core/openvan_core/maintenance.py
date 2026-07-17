"""Maintenance & service reminders.

Van life is hard on a vehicle (heavy build, long miles) and the habitation side
needs its own care — gas tightness, damp checks, testing the CO/smoke alarms. It's
easy to lose track. This keeps a small schedule of odometer- and date-based items,
tells you what's due, and lets you tick one off (which resets its next-due). Local
and offline; persists to the config store so it survives restarts.

Assumption: default intervals are sensible generic values (engine service ~15 000
km, habitation/damp check yearly, alarm test twice a year). A real deployment would
let the user edit intervals — see the backlog.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any, Callable

_NS = "maintenance"

# (id, label, kind, interval)  — interval is km for "odometer", days for "date".
DEFAULT_ITEMS = [
    ("engine_service", "Engine service", "odometer", 15000.0),
    ("tyre_rotation", "Tyre rotation", "odometer", 10000.0),
    ("brake_check", "Brake inspection", "odometer", 30000.0),
    ("gas_inspection", "Gas system inspection", "date", 365.0),
    ("damp_check", "Habitation / damp check", "date", 365.0),
    ("alarm_test", "Test CO & smoke alarms", "date", 180.0),
]


@dataclass
class MaintenanceItem:
    id: str
    label: str
    kind: str  # "odometer" | "date"
    interval: float
    last_km: float | None = None
    last_iso: str | None = None


class MaintenanceLog:
    def __init__(
        self,
        store: Any,
        get_odometer: Callable[[], float | None],
        intervals: dict[str, float] | None = None,
    ) -> None:
        self.store = store
        self.get_odometer = get_odometer
        # Per-item interval overrides (km or days), keyed by item id. Defaults win
        # when an id is absent, so nothing is hardcoded beyond the fallback.
        self.intervals = intervals or {}
        self.items: dict[str, MaintenanceItem] = {}

    def load(self) -> None:
        saved = {}
        if self.store is not None:
            for row in (self.store.get_all(_NS).get("items") or []):
                saved[row.get("id")] = row
        self.items = {}
        for item_id, label, kind, interval in DEFAULT_ITEMS:
            row = saved.get(item_id, {})
            self.items[item_id] = MaintenanceItem(
                item_id, label, kind, float(self.intervals.get(item_id, interval)),
                row.get("last_km"), row.get("last_iso"),
            )

    def _persist(self) -> None:
        if self.store is not None:
            self.store.set_many(_NS, {"items": [asdict(i) for i in self.items.values()]})

    def status(self, odometer_km: float | None, today: date) -> list[dict[str, Any]]:
        odo = odometer_km if odometer_km is not None else 0.0
        out: list[dict[str, Any]] = []
        for it in self.items.values():
            entry: dict[str, Any] = {"id": it.id, "label": it.label, "kind": it.kind}
            if it.kind == "odometer":
                # With no recorded service, baseline to the current interval window so
                # a used van shows a realistic "due in N km", not instantly overdue.
                base = it.last_km if it.last_km is not None else (odo // it.interval) * it.interval
                next_km = base + it.interval
                remaining = next_km - odo
                entry.update(
                    remaining_km=round(remaining),
                    next_km=round(next_km),
                    due=remaining <= 0,
                )
            else:
                base_iso = it.last_iso or today.isoformat()
                base = date.fromisoformat(base_iso)
                next_date = base + timedelta(days=it.interval)
                remaining_days = (next_date - today).days
                entry.update(
                    remaining_days=remaining_days,
                    next_iso=next_date.isoformat(),
                    due=remaining_days <= 0,
                )
            out.append(entry)
        return out

    def complete(self, item_id: str, odometer_km: float | None, today: date) -> bool:
        it = self.items.get(item_id)
        if it is None:
            return False
        if it.kind == "odometer":
            it.last_km = odometer_km if odometer_km is not None else 0.0
        else:
            it.last_iso = today.isoformat()
        self._persist()
        return True
