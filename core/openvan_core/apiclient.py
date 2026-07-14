"""Async HTTP client for the OpenVan Core REST API.

Thin, dependency-light (httpx only) wrapper used by the MCP server so it bridges
to a *running* Core over HTTP — true parity with the REST API, and no second Core
fighting over the sim loops or SQLite files. Also handy for scripts and tests.
"""

from __future__ import annotations

from typing import Any

import httpx


class OpenVanClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client
        self._timeout = timeout

    async def _request(self, method: str, path: str, **kw: Any) -> Any:
        if self._client is not None:
            resp = await self._client.request(method, path, **kw)
        else:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self._timeout) as c:
                resp = await c.request(method, path, **kw)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        return resp.json() if ctype.startswith("application/json") else resp.text

    def _get(self, path: str, params: dict | None = None):
        return self._request("GET", path, params=params)

    def _post(self, path: str, json: dict | None = None):
        return self._request("POST", path, json=json)

    # --- state & control -------------------------------------------------
    def get_state(self):
        return self._get("/api/state")

    async def list_devices(self) -> list[dict]:
        state = await self.get_state()
        return [
            {"entity_id": e["entity_id"], "name": e["name"], "commands": e["commands"], "state": e["state"]}
            for e in state.get("entities", [])
            if e.get("controllable")
        ]

    def execute_intent(self, entity_id: str, command: str, params: dict | None = None):
        return self._post(
            "/api/intent",
            {"entity_id": entity_id, "command": command, "params": params or {}},
        )

    def command_text(self, text: str):
        return self._post("/api/intent/text", {"text": text})

    def inject_signal(self, key: str, value: Any):
        return self._post("/api/sim/signal", {"key": key, "value": value})

    # --- companion -------------------------------------------------------
    def get_notices(self):
        return self._get("/api/notices")

    def briefing(self):
        return self._post("/api/briefing")

    # --- telemetry / predictions / weather -------------------------------
    def get_predictions(self):
        return self._get("/api/telemetry/predictions")

    def get_weather(self):
        return self._get("/api/weather")

    def get_series(self, key: str, minutes: float = 60.0, bucket: float | None = None):
        params: dict[str, Any] = {"key": key, "minutes": minutes}
        if bucket:
            params["bucket"] = bucket
        return self._get("/api/telemetry/series", params)

    # --- travel memory ---------------------------------------------------
    def get_stays(self):
        return self._get("/api/memory/stays")

    def bookmark(self, note: str = ""):
        return self._post("/api/memory/bookmark", {"note": note})

    def add_note(self, text: str):
        return self._post("/api/memory/note", {"text": text})

    def name_place(self, name: str):
        return self._post("/api/memory/place", {"name": name})

    # --- settings & personalities ----------------------------------------
    def get_settings(self):
        return self._get("/api/settings")

    def update_settings(self, **fields: Any):
        return self._post("/api/settings", {k: v for k, v in fields.items() if v is not None})

    def list_personalities(self):
        return self._get("/api/personalities")

    def set_personality(self, personality_id: str):
        return self._post("/api/personalities/active", {"id": personality_id})
