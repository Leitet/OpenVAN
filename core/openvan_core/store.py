"""Local config store — the persistent home for plugin / camp-source settings,
including credentials.

Plugin details (API keys, endpoints, …) live here, in the local **database**, not
in environment variables: the user configures a source in the app and the value
survives restarts and travels with the install. Stdlib ``sqlite3`` (no dependency,
offline-first), a single ``config(namespace, key, value)`` table with JSON-encoded
values. Access is tiny and infrequent, so it's synchronous under a lock.

Namespaces keep providers apart, e.g. ``camp:park4night`` or ``plugin:water_system``.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ConfigStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS config ("
            "  ns TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,"
            "  PRIMARY KEY (ns, key))"
        )
        self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def get(self, ns: str, key: str, default: Any = None) -> Any:
        if self._conn is None:
            return default
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM config WHERE ns=? AND key=?", (ns, key)
            ).fetchone()
        return json.loads(row[0]) if row else default

    def get_all(self, ns: str) -> dict[str, Any]:
        if self._conn is None:
            return {}
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, value FROM config WHERE ns=?", (ns,)
            ).fetchall()
        return {k: json.loads(v) for k, v in rows}

    def set_many(self, ns: str, values: dict[str, Any]) -> None:
        if self._conn is None:
            return
        with self._lock:
            for key, value in values.items():
                self._conn.execute(
                    "INSERT OR REPLACE INTO config (ns, key, value) VALUES (?, ?, ?)",
                    (ns, key, json.dumps(value)),
                )
            self._conn.commit()
