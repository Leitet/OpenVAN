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
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
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


class SettingsBody(BaseModel):
    ai_enabled: bool | None = None
    default_connectivity: str | None = None
    offline_model: str | None = None
    offline_base_url: str | None = None
    online_provider: str | None = None
    online_model: str | None = None
    online_base_url: str | None = None
    online_api_key: str | None = None
    simulate: bool | None = None


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
    connectivity: str | None = None
    model: str | None = None
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
    config = config or Config.from_env()
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
