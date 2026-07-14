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
        # Aggregated buckets for long retention (raw is pruned after days; these
        # keep hourly/daily history for months without bloating the DB).
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS rollups ("
            "key TEXT NOT NULL, period TEXT NOT NULL, bucket REAL NOT NULL, "
            "count INTEGER NOT NULL, sum REAL NOT NULL, min REAL NOT NULL, "
            "max REAL NOT NULL, PRIMARY KEY (key, period, bucket))"
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

    # --- rollups (write-time aggregation for long retention) -------------
    def rollup(self) -> None:
        """Aggregate current raw samples into hourly + daily buckets (upsert).

        Runs before raw pruning, so each window is captured before its raw rows
        expire; older buckets already computed are left untouched.
        """
        if self._conn is None:
            return
        with self._lock:
            for period, width in (("hour", 3600.0), ("day", 86400.0)):
                # width/period are trusted constants (safe to inline).
                self._conn.execute(
                    f"INSERT OR REPLACE INTO rollups"
                    f"(key, period, bucket, count, sum, min, max) "
                    f"SELECT key, '{period}', CAST(ts / {width} AS INT) * {width}, "
                    f"COUNT(*), SUM(value), MIN(value), MAX(value) "
                    f"FROM samples GROUP BY key, CAST(ts / {width} AS INT)"
                )
            self._conn.commit()

    def series_agg(
        self,
        key: str,
        period: str,
        since_ts: float,
        until_ts: float | None = None,
        limit: int = 5000,
    ) -> list[dict[str, float]]:
        """Read averaged rollup buckets (with min/max) for a signal."""
        if self._conn is None:
            return []
        until_ts = until_ts if until_ts is not None else _FAR_FUTURE
        with self._lock:
            rows = self._conn.execute(
                "SELECT bucket, sum, count, min, max FROM rollups "
                "WHERE key = ? AND period = ? AND bucket >= ? AND bucket <= ? "
                "ORDER BY bucket LIMIT ?",
                (key, period, since_ts, until_ts, limit),
            ).fetchall()
        return [
            {
                "t": round(r[0], 3),
                "v": r[1] / r[2] if r[2] else 0.0,
                "min": r[3],
                "max": r[4],
            }
            for r in rows
        ]

    def prune_rollups(self, older_than_ts: float) -> int:
        if self._conn is None:
            return 0
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM rollups WHERE bucket < ?", (older_than_ts,)
            )
            self._conn.commit()
            return cur.rowcount


class TelemetryRecorder:
    """Records twin signal changes and periodically rolls up + prunes."""

    def __init__(
        self,
        bus: EventBus,
        store: TelemetryStore,
        *,
        roll_interval: float = 600.0,
        raw_retention_days: float = 7.0,
        rollup_retention_days: float = 365.0,
    ) -> None:
        self.bus = bus
        self.store = store
        self.roll_interval = roll_interval
        self.raw_retention_days = raw_retention_days
        self.rollup_retention_days = rollup_retention_days
        self._unsubscribe = None
        self._task = None

    def start(self) -> None:
        import asyncio

        self._unsubscribe = self.bus.subscribe(SIGNAL_CHANGED, self._on_signal)
        self._task = asyncio.create_task(self._maintain())

    async def _on_signal(self, event) -> None:
        import asyncio
        import time

        key = event.data.get("key")
        value = event.data.get("value")
        if key is None:
            return
        await asyncio.to_thread(self.store.record, key, value, time.time())

    async def _maintain(self) -> None:
        import asyncio
        import time

        while True:
            # Roll up first, then prune raw, then prune old rollups.
            await asyncio.to_thread(self.store.rollup)
            now = time.time()
            await asyncio.to_thread(
                self.store.prune, now - self.raw_retention_days * 86400
            )
            await asyncio.to_thread(
                self.store.prune_rollups, now - self.rollup_retention_days * 86400
            )
            await asyncio.sleep(self.roll_interval)

    async def stop(self) -> None:
        import asyncio

        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
