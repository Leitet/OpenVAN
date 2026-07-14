"""Travel memory — a living journal of the journey.

Automatically logs *stays*: when the van parks (ignition off / stopped) for a
while it opens a stay at the current GPS, capturing the weather and battery
state; when it drives off the stay closes with its duration and energy used.
Users can add notes, name a place, or bookmark the current spot instantly. Stored
locally in SQLite (offline-first) and surfaced to the companion so it can recall
past trips ("remember that lake we stayed at?").
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_COLS = (
    "id, lat, lon, place, started_at, ended_at, "
    "arrival_soc, departure_soc, solar_wh, weather, notes"
)


def _f(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


class TravelMemory:
    def __init__(self, config: Any, twin: Any, weather: Any = None, telemetry: Any = None):
        self.config = config
        self.twin = twin
        self.weather = weather
        self.telemetry = telemetry
        self.dwell_s = config.memory_dwell_s
        self.check_s = config.memory_check_s
        self.path = Path(config.data_dir) / "journal.db"
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._task: asyncio.Task | None = None
        self._stationary_since: float | None = None
        self._open_id: int | None = None

    # --- lifecycle -------------------------------------------------------
    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS stays ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, lat REAL, lon REAL, place TEXT, "
            "started_at REAL, ended_at REAL, arrival_soc REAL, departure_soc REAL, "
            "solar_wh REAL, weather TEXT, notes TEXT)"
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT id FROM stays WHERE ended_at IS NULL ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        self._open_id = row[0] if row else None

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    async def start(self) -> None:
        await asyncio.to_thread(self.open)
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await asyncio.to_thread(self.close)

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.check_s)
            await asyncio.to_thread(self.tick, time.time())

    # --- stay detection --------------------------------------------------
    def tick(self, now: float) -> None:
        speed = _f(self.twin.get("vehicle.speed_kmh")) or 0.0
        moving = bool(self.twin.get("vehicle.ignition")) and speed > 0
        if moving:
            if self._open_id is not None:
                self._close(self._open_id, now)
            self._stationary_since = None
            return
        if self._stationary_since is None:
            self._stationary_since = now
        if self._open_id is None and (now - self._stationary_since) >= self.dwell_s:
            self._open(now)

    def _weather_json(self) -> str:
        return json.dumps(self.weather.snapshot()) if self.weather is not None else "{}"

    def _open(self, now: float) -> None:
        if self._conn is None:
            return
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO stays (lat, lon, started_at, arrival_soc, weather, notes) "
                "VALUES (?, ?, ?, ?, ?, '')",
                (
                    _f(self.twin.get("gps.lat")),
                    _f(self.twin.get("gps.lon")),
                    now,
                    _f(self.twin.get("house_battery.soc")),
                    self._weather_json(),
                ),
            )
            self._conn.commit()
            self._open_id = cur.lastrowid

    def _close(self, stay_id: int, now: float) -> None:
        if self._conn is None:
            return
        solar_wh = None
        with self._lock:
            row = self._conn.execute(
                "SELECT started_at FROM stays WHERE id = ?", (stay_id,)
            ).fetchone()
        if row and self.telemetry is not None:
            solar_wh = round(self.telemetry.integral("solar.power", row[0], now) / 3600.0, 1)
        with self._lock:
            self._conn.execute(
                "UPDATE stays SET ended_at = ?, departure_soc = ?, solar_wh = ? WHERE id = ?",
                (now, _f(self.twin.get("house_battery.soc")), solar_wh, stay_id),
            )
            self._conn.commit()
        self._open_id = None
        self._stationary_since = None

    # --- manual actions --------------------------------------------------
    def bookmark(self, note: str = "") -> dict[str, Any] | None:
        if self._conn is None:
            return None
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO stays "
                "(lat, lon, started_at, ended_at, arrival_soc, departure_soc, weather, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    _f(self.twin.get("gps.lat")),
                    _f(self.twin.get("gps.lon")),
                    now,
                    now,
                    _f(self.twin.get("house_battery.soc")),
                    _f(self.twin.get("house_battery.soc")),
                    self._weather_json(),
                    note,
                ),
            )
            self._conn.commit()
            new_id = cur.lastrowid
        return self._fetch(new_id)

    def _target_id(self) -> int | None:
        # The most-recently-created stay (a fresh bookmark wins over an
        # already-open auto-stay), matching the top of the journal list.
        if self._conn is None:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM stays ORDER BY started_at DESC, id DESC LIMIT 1"
            ).fetchone()
        return row[0] if row else None

    def add_note(self, text: str) -> dict[str, Any] | None:
        sid = self._target_id()
        if sid is None or self._conn is None:
            return None
        with self._lock:
            row = self._conn.execute("SELECT notes FROM stays WHERE id = ?", (sid,)).fetchone()
            existing = (row[0] if row else "") or ""
            merged = f"{existing}\n{text}".strip() if existing else text
            self._conn.execute("UPDATE stays SET notes = ? WHERE id = ?", (merged, sid))
            self._conn.commit()
        return self._fetch(sid)

    def set_place(self, name: str) -> dict[str, Any] | None:
        sid = self._target_id()
        if sid is None or self._conn is None:
            return None
        with self._lock:
            self._conn.execute("UPDATE stays SET place = ? WHERE id = ?", (name, sid))
            self._conn.commit()
        return self._fetch(sid)

    def delete(self, stay_id: int) -> bool:
        if self._conn is None:
            return False
        with self._lock:
            cur = self._conn.execute("DELETE FROM stays WHERE id = ?", (stay_id,))
            self._conn.commit()
        if self._open_id == stay_id:
            self._open_id = None
        return cur.rowcount > 0

    # --- reads -----------------------------------------------------------
    def list_stays(self, limit: int = 50) -> list[dict[str, Any]]:
        if self._conn is None:
            return []
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {_COLS} FROM stays ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row(r) for r in rows]

    def current(self) -> dict[str, Any] | None:
        return self._fetch(self._open_id) if self._open_id is not None else None

    def _fetch(self, stay_id: int | None) -> dict[str, Any] | None:
        if stay_id is None or self._conn is None:
            return None
        with self._lock:
            row = self._conn.execute(
                f"SELECT {_COLS} FROM stays WHERE id = ?", (stay_id,)
            ).fetchone()
        return self._row(row) if row else None

    def _row(self, r) -> dict[str, Any]:
        started, ended = r[4], r[5]
        end_or_now = ended if ended is not None else time.time()
        duration_h = (end_or_now - started) / 3600.0 if started else None
        arrival, departure = r[6], r[7]
        soc_used = (
            round(arrival - departure, 1)
            if arrival is not None and departure is not None
            else None
        )
        try:
            weather = json.loads(r[9] or "{}")
        except ValueError:
            weather = {}
        return {
            "id": r[0],
            "lat": r[1],
            "lon": r[2],
            "place": r[3],
            "started_at": started,
            "ended_at": ended,
            "open": ended is None,
            "duration_hours": round(duration_h, 2) if duration_h is not None else None,
            "arrival_soc": arrival,
            "departure_soc": departure,
            "soc_used_pct": soc_used,
            "solar_wh": r[8],
            "condition": (weather.get("current") or {}).get("condition"),
            "notes": r[10] or "",
        }
