"""Local HTTP + WebSocket API.

This is the surface the web simulator (and, later, mobile/tablet/voice clients)
talk to. Everything is served locally — the API is an enhancement to the offline
core, never a dependency of it.

Endpoints
---------
GET  /api/health              liveness
GET  /api/state               entities + twin snapshot
POST /api/intent              execute a structured intent (safety-checked)
POST /api/intent/text         resolve natural language, then execute
POST /api/sim/signal          simulator injects a raw hardware signal
WS   /ws                      live stream of every Core event
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import Config
from .events import Event
from .intents import Intent
from .runtime import Core, build_core

logger = logging.getLogger(__name__)


class IntentBody(BaseModel):
    entity_id: str
    command: str
    params: dict[str, Any] = {}
    source: str = "api"


class TextBody(BaseModel):
    text: str


class SignalBody(BaseModel):
    key: str
    value: Any


class WeatherSimBody(BaseModel):
    scenario: str = "rain"


class NoteBody(BaseModel):
    text: str


class PlaceBody(BaseModel):
    name: str


class BookmarkBody(BaseModel):
    note: str = ""


class SettingsBody(BaseModel):
    ai_enabled: bool | None = None
    connectivity: str | None = None
    language: str | None = None
    offline_model: str | None = None
    offline_base_url: str | None = None
    online_provider: str | None = None
    online_model: str | None = None
    online_base_url: str | None = None
    online_api_key: str | None = None
    simulate: bool | None = None


class CampSourceBody(BaseModel):
    id: str
    enabled: bool


class CampSourceConfigBody(BaseModel):
    id: str
    config: dict[str, Any]


class ActivePersonalityBody(BaseModel):
    id: str


class ForkPersonalityBody(BaseModel):
    base_id: str
    name: str


class PersonalityUpdateBody(BaseModel):
    name: str | None = None
    category: str | None = None
    tagline: str | None = None
    traits: list[str] | None = None
    inspiration: list[str] | None = None
    style: str | None = None
    examples: list[str] | None = None


class _WebSocketHub:
    """Fans every Core event out to connected simulator clients."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, event: Event) -> None:
        message = {"topic": event.topic, "data": event.data}
        async with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                await ws.send_json(message)
            except Exception:
                await self.disconnect(ws)


def build_app(config: Config | None = None, core: Core | None = None) -> FastAPI:
    config = config or Config.resolve()
    core = core or build_core(config)
    ws_hub = _WebSocketHub()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        core.bus.subscribe("*", ws_hub.broadcast)
        await core.start()
        yield
        await core.stop()

    app = FastAPI(title="OpenVan Core", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # local-only service; simulator runs on a dev port
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.core = core

    def _state_snapshot() -> dict[str, Any]:
        return {
            "entities": [e.as_dict() for e in core.hub.entities.values()],
            "twin": core.twin.snapshot(),
            "notices": core.advisors.active_notices(),
            "assistant": core.assistant_state(),
        }

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        return _state_snapshot()

    @app.post("/api/intent")
    async def intent(body: IntentBody) -> dict[str, Any]:
        result = await core.hub.execute_intent(
            Intent(body.entity_id, body.command, body.params, body.source)
        )
        return result.as_dict()

    @app.post("/api/intent/text")
    async def intent_text(body: TextBody) -> dict[str, Any]:
        result = await core.hub.execute_text(body.text)
        return result.as_dict()

    @app.post("/api/chat")
    async def chat(body: TextBody) -> dict[str, Any]:
        # Conversational: runs a command (safety-checked) or answers from state.
        return await core.chat(body.text)

    @app.get("/api/camp/search")
    async def camp_search(radius: float | None = None) -> dict[str, Any]:
        if not core.config.camp_enabled:
            return {"location": None, "spots": []}
        return await core.camp.search(radius)

    @app.get("/api/camp/sources")
    async def camp_sources() -> dict[str, Any]:
        return {"sources": core.camp.source_infos()}

    @app.post("/api/camp/sources")
    async def set_camp_source(body: CampSourceBody) -> dict[str, Any]:
        if not await core.set_camp_source(body.id, body.enabled):
            raise HTTPException(404, f"unknown camp source '{body.id}'")
        return {"sources": core.camp.source_infos()}

    @app.post("/api/camp/sources/config")
    async def set_camp_source_config(body: CampSourceConfigBody) -> dict[str, Any]:
        if not await core.set_camp_source_config(body.id, body.config):
            raise HTTPException(404, f"unknown camp source '{body.id}'")
        return {"sources": core.camp.source_infos()}

    @app.post("/api/sim/signal")
    async def sim_signal(body: SignalBody) -> dict[str, str]:
        await core.twin.set_signal(body.key, body.value, source="sim")
        return {"status": "ok"}

    @app.get("/api/notices")
    async def notices() -> dict[str, Any]:
        return {"notices": core.advisors.active_notices()}

    @app.post("/api/briefing")
    async def briefing() -> dict[str, str]:
        text = await core.companion.briefing(
            core.hub,
            core.advisors.active_notices(),
            use_llm=getattr(core.hub.resolver, "active", False),
            persona=core.personalities.get_active().style,
            language=core.config.language,
        )
        return {"text": text}

    @app.get("/api/personalities")
    async def list_personalities() -> dict[str, Any]:
        return {
            "active": core.personalities.active_id(),
            "personalities": [p.as_dict() for p in core.personalities.all()],
        }

    @app.post("/api/personalities/active")
    async def set_personality(body: ActivePersonalityBody) -> dict[str, Any]:
        if not core.personalities.set_active(body.id):
            raise HTTPException(404, f"unknown personality '{body.id}'")
        await core.bus.publish("assistant.changed", core.assistant_state())
        return {"active": core.personalities.active_id()}

    @app.post("/api/personalities/fork")
    async def fork_personality(body: ForkPersonalityBody) -> dict[str, Any]:
        forked = core.personalities.fork(body.base_id, body.name)
        if forked is None:
            raise HTTPException(404, f"unknown base personality '{body.base_id}'")
        return forked.as_dict()

    @app.put("/api/personalities/{pid}")
    async def update_personality(pid: str, body: PersonalityUpdateBody) -> dict[str, Any]:
        updated = core.personalities.update(pid, **body.model_dump(exclude_none=True))
        if updated is None:
            raise HTTPException(404, "unknown or built-in personality (built-ins are read-only)")
        if pid == core.personalities.active_id():
            await core.bus.publish("assistant.changed", core.assistant_state())
        return updated.as_dict()

    @app.delete("/api/personalities/{pid}")
    async def delete_personality(pid: str) -> dict[str, Any]:
        if not core.personalities.delete(pid):
            raise HTTPException(404, "unknown or built-in personality (built-ins cannot be deleted)")
        await core.bus.publish("assistant.changed", core.assistant_state())
        return {"active": core.personalities.active_id()}

    @app.get("/api/settings")
    async def get_settings() -> dict[str, Any]:
        return core.settings()

    @app.post("/api/settings")
    async def update_settings(body: SettingsBody) -> dict[str, Any]:
        return await core.apply_settings(**body.model_dump(exclude_none=True))

    @app.get("/api/models")
    async def models(connectivity: str = "offline") -> dict[str, Any]:
        return {"models": await core.available_models(connectivity)}

    @app.get("/api/telemetry/keys")
    async def telemetry_keys() -> dict[str, Any]:
        if not core.config.telemetry_enabled:
            return {"keys": []}
        return {"keys": await asyncio.to_thread(core.telemetry.keys)}

    @app.get("/api/telemetry/series")
    async def telemetry_series(
        key: str, minutes: float = 60.0, bucket: float | None = None
    ) -> dict[str, Any]:
        if not core.config.telemetry_enabled:
            return {"key": key, "points": []}
        since = time.time() - minutes * 60.0
        # Long ranges read pre-aggregated rollups; short ranges read raw.
        if minutes > 43200:  # > 30 days -> daily buckets
            points = await asyncio.to_thread(core.telemetry.series_agg, key, "day", since)
        elif minutes > 1440:  # > 24 hours -> hourly buckets
            points = await asyncio.to_thread(core.telemetry.series_agg, key, "hour", since)
        else:
            points = await asyncio.to_thread(
                core.telemetry.series, key, since, None, bucket
            )
        return {"key": key, "points": points}

    @app.get("/api/weather")
    async def weather() -> dict[str, Any]:
        if not core.config.weather_enabled:
            return {}
        return core.weather.snapshot()

    @app.post("/api/weather/refresh")
    async def weather_refresh() -> dict[str, Any]:
        if not core.config.weather_enabled:
            return {}
        await core.weather.refresh()
        return core.weather.snapshot()

    @app.post("/api/weather/simulate")
    async def weather_simulate(body: WeatherSimBody) -> dict[str, Any]:
        if not core.config.weather_enabled:
            return {}
        return await core.weather.simulate(body.scenario)

    @app.get("/api/memory/stays")
    async def memory_stays(limit: int = 50) -> dict[str, Any]:
        if not core.config.memory_enabled:
            return {"stays": [], "current": None}
        stays = await asyncio.to_thread(core.memory.list_stays, limit)
        current = await asyncio.to_thread(core.memory.current)
        return {"stays": stays, "current": current}

    @app.post("/api/memory/bookmark")
    async def memory_bookmark(body: BookmarkBody) -> dict[str, Any]:
        if not core.config.memory_enabled:
            raise HTTPException(400, "travel memory is disabled")
        stay = await asyncio.to_thread(core.memory.bookmark, body.note)
        return stay or {}

    @app.post("/api/memory/note")
    async def memory_note(body: NoteBody) -> dict[str, Any]:
        if not core.config.memory_enabled:
            raise HTTPException(400, "travel memory is disabled")
        stay = await asyncio.to_thread(core.memory.add_note, body.text)
        if stay is None:
            raise HTTPException(404, "no stay to annotate")
        return stay

    @app.post("/api/memory/place")
    async def memory_place(body: PlaceBody) -> dict[str, Any]:
        if not core.config.memory_enabled:
            raise HTTPException(400, "travel memory is disabled")
        stay = await asyncio.to_thread(core.memory.set_place, body.name)
        if stay is None:
            raise HTTPException(404, "no stay to name")
        return stay

    @app.delete("/api/memory/stays/{stay_id}")
    async def memory_delete(stay_id: int) -> dict[str, bool]:
        if not core.config.memory_enabled:
            raise HTTPException(400, "travel memory is disabled")
        return {"deleted": await asyncio.to_thread(core.memory.delete, stay_id)}

    @app.get("/api/telemetry/predictions")
    async def telemetry_predictions() -> dict[str, Any]:
        return await asyncio.to_thread(core.predictions)

    @app.get("/api/telemetry/export")
    async def telemetry_export(key: str | None = None, minutes: float = 1440.0) -> Response:
        if not core.config.telemetry_enabled:
            return Response("", media_type="text/csv")
        since = time.time() - minutes * 60.0
        rows = await asyncio.to_thread(
            core.telemetry.export, since, None, [key] if key else None
        )
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["key", "timestamp", "iso", "value"])
        for k, ts, value in rows:
            iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            writer.writerow([k, f"{ts:.3f}", iso, value])
        filename = f"openvan-telemetry-{key or 'all'}.csv"
        return Response(
            buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws_hub.connect(ws)
        try:
            await ws.send_json({"topic": "snapshot", "data": _state_snapshot()})
            while True:
                # We don't expect inbound messages; keep the socket alive.
                await ws.receive_text()
        except WebSocketDisconnect:
            await ws_hub.disconnect(ws)
        except Exception:
            await ws_hub.disconnect(ws)

    return app
