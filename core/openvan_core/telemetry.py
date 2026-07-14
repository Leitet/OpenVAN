"""Local time-series telemetry.

Records every numeric twin signal over time to a local SQLite database — the raw
hardware layer is exactly where history belongs. Offline-first: a plain file on
disk, no server, no heavy TSDB. This history powers graphs, trends and
predictions (battery drain rate, water usage, solar), and feeds the AI richer
context than a single instantaneous reading.

SQLite is stdlib (no dependency) and comfortably handles a van's write rate. All
DB access is guarded by a lock and driven off the event loop via
``asyncio.to_thread`` so recording never blocks Core.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from .events import EventBus
from .twin import SIGNAL_CHANGED

_FAR_FUTURE = 4102444800.0  # ~year 2100, used as an open upper bound


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class TelemetryStore:
    def __init__(self, path: Path | str, retention_days: float = 7.0) -> None:
        self.path = Path(path)
        self.retention_days = retention_days
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS samples "
            "(key TEXT NOT NULL, ts REAL NOT NULL, value REAL NOT NULL)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_samples_key_ts ON samples(key, ts)"
        )
        self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def record(self, key: str, value: Any, ts: float) -> None:
        number = _to_float(value)
        if number is None or self._conn is None:
            return
        with self._lock:
            self._conn.execute(
                "INSERT INTO samples(key, ts, value) VALUES (?, ?, ?)",
                (key, ts, number),
            )
            self._conn.commit()

    def keys(self) -> list[str]:
        if self._conn is None:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT key FROM samples ORDER BY key"
            ).fetchall()
        return [r[0] for r in rows]

    def series(
        self,
        key: str,
        since_ts: float,
        until_ts: float | None = None,
        bucket: float | None = None,
        limit: int = 5000,
    ) -> list[dict[str, float]]:
        if self._conn is None:
            return []
        until_ts = until_ts if until_ts is not None else _FAR_FUTURE
        with self._lock:
            if bucket and bucket > 0:
                # Read-time downsampling: average within fixed-width time buckets.
                rows = self._conn.execute(
                    "SELECT CAST(ts / ? AS INT) * ? AS b, AVG(value) "
                    "FROM samples WHERE key = ? AND ts >= ? AND ts <= ? "
                    "GROUP BY b ORDER BY b LIMIT ?",
                    (bucket, bucket, key, since_ts, until_ts, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT ts, value FROM samples "
                    "WHERE key = ? AND ts >= ? AND ts <= ? ORDER BY ts LIMIT ?",
                    (key, since_ts, until_ts, limit),
                ).fetchall()
        return [{"t": round(r[0], 3), "v": r[1]} for r in rows]

    def rate_per_hour(self, key: str, since_ts: float) -> float | None:
        """Change in ``key`` per hour over the window (first vs latest sample)."""
        if self._conn is None:
            return None
        with self._lock:
            first = self._conn.execute(
                "SELECT ts, value FROM samples WHERE key = ? AND ts >= ? "
                "ORDER BY ts LIMIT 1",
                (key, since_ts),
            ).fetchone()
            last = self._conn.execute(
                "SELECT ts, value FROM samples WHERE key = ? ORDER BY ts DESC LIMIT 1",
                (key,),
            ).fetchone()
        if not first or not last:
            return None
        hours = (last[0] - first[0]) / 3600.0
        if hours <= 0:
            return None
        return (last[1] - first[1]) / hours

    def export(
        self,
        since_ts: float,
        until_ts: float | None = None,
        keys: list[str] | None = None,
    ) -> list[tuple[str, float, float]]:
        """Rows of (key, ts, value) for export, ordered by time."""
        if self._conn is None:
            return []
        until_ts = until_ts if until_ts is not None else _FAR_FUTURE
        with self._lock:
            if keys:
                placeholders = ",".join("?" * len(keys))
                rows = self._conn.execute(
                    f"SELECT key, ts, value FROM samples "
                    f"WHERE key IN ({placeholders}) AND ts >= ? AND ts <= ? ORDER BY ts",
                    (*keys, since_ts, until_ts),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT key, ts, value FROM samples "
                    "WHERE ts >= ? AND ts <= ? ORDER BY ts",
                    (since_ts, until_ts),
                ).fetchall()
        return [(r[0], r[1], r[2]) for r in rows]

    def prune(self, older_than_ts: float) -> int:
        if self._conn is None:
            return 0
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM samples WHERE ts < ?", (older_than_ts,)
            )
            self._conn.commit()
            return cur.rowcount


class TelemetryRecorder:
    """Subscribes to twin signal changes and writes them to the store."""

    def __init__(self, bus: EventBus, store: TelemetryStore) -> None:
        self.bus = bus
        self.store = store
        self._unsubscribe = None

    def start(self) -> None:
        self._unsubscribe = self.bus.subscribe(SIGNAL_CHANGED, self._on_signal)

    async def _on_signal(self, event) -> None:
        import asyncio
        import time

        key = event.data.get("key")
        value = event.data.get("value")
        if key is None:
            return
        await asyncio.to_thread(self.store.record, key, value, time.time())

    async def stop(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
