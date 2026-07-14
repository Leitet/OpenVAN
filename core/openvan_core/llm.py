"""Local, model-agnostic LLM assistant.

The AI's only job is to turn natural language into a *proposed* ``Intent``. It
never touches hardware — OpenVan Core still safety-checks whatever the model
suggests (Rule 2). And it is strictly optional (Rule 3, offline-first): if no
model is reachable, the resolver falls back to the rule-based
:class:`~openvan_core.intents.IntentResolver`, so text commands keep working.

The default client targets **Ollama** (a local model runtime), but any client
implementing ``available`` + ``chat_json`` plugs in — local, cloud, or hybrid
(Rule 4, model-agnostic).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

import httpx

from .entities import Entity
from .intents import Intent, IntentResolver

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are OpenVan's in-vehicle assistant. Convert the user's request into ONE
control action for a single device.

You do NOT control hardware. You only propose an action; OpenVan independently
safety-checks it (battery, fuel, water, etc.) and may refuse it.

You are given `devices` (controllable — each lists its allowed `commands`) and
`context` (read-only sensor readings, for your understanding only).

Respond with JSON ONLY, no prose:
{"entity_id": "<a device entity_id, or null>", "command": "<one of that device's commands>", "params": {}}

Rules:
- Use only an entity_id and command that appear in `devices`.
- Infer the device from the user's underlying need, not just explicit names:
  wanting water or to wash → the water pump; feeling cold → the heater;
  it being dark → a light. Map the need to the single most relevant device.
- If genuinely nothing fits, respond {"entity_id": null}.
- For a temperature setpoint, use command "set_temperature" with
  params {"temperature": <number in Celsius>}.
- Choose the single best action. Never invent devices or commands.
"""


class LLMClient(Protocol):
    async def available(self) -> bool: ...
    async def chat_json(self, system: str, user: str) -> str | None: ...
    async def chat_text(self, system: str, user: str) -> str | None: ...


class OllamaClient:
    """Talks to a local Ollama server (https://ollama.com)."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "llama3.2",
        timeout: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            return []

    async def chat_json(self, system: str, user: str) -> str | None:
        return await self._chat(system, user, json_format=True, temperature=0.0)

    async def chat_text(self, system: str, user: str) -> str | None:
        return await self._chat(system, user, json_format=False, temperature=0.6)

    async def _chat(
        self, system: str, user: str, *, json_format: bool, temperature: float
    ) -> str | None:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_format:
            payload["format"] = "json"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
                resp.raise_for_status()
                return resp.json().get("message", {}).get("content")
        except Exception as exc:
            logger.warning("LLM call failed: %r", exc)
            return None


class LLMIntentResolver(IntentResolver):
    """Resolve text to an Intent via an LLM, falling back to rules when needed."""

    def __init__(self, client: LLMClient, fallback: IntentResolver | None = None) -> None:
        self.client = client
        self.fallback = fallback or IntentResolver()
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def model(self) -> str | None:
        return getattr(self.client, "model", None) if self._active else None

    async def startup(self) -> None:
        self._active = await self.client.available()
        if self._active:
            logger.info("AI intent resolver active (model=%s)", self.model)
        else:
            logger.info("AI resolver unavailable — using offline rule-based resolver")

    def deactivate(self) -> None:
        self._active = False

    async def resolve(self, text: str, entities: dict[str, Any]) -> Intent | None:
        if self._active:
            intent = await self._llm_resolve(text, entities)
            if intent is not None:
                return intent
        return await self.fallback.resolve(text, entities)

    async def _llm_resolve(
        self, text: str, entities: dict[str, Entity]
    ) -> Intent | None:
        controllable = {eid: e for eid, e in entities.items() if e.controllable}
        if not controllable:
            return None
        devices = [
            {
                "entity_id": e.entity_id,
                "name": e.name,
                "category": e.category,
                "commands": e.commands,
                "state": e.state,
            }
            for e in controllable.values()
        ]
        context = [
            {"entity_id": e.entity_id, "name": e.name, "state": e.state, "unit": e.unit}
            for e in entities.values()
            if not e.controllable
        ]
        user = json.dumps({"request": text, "devices": devices, "context": context})
        raw = await self.client.chat_json(SYSTEM_PROMPT, user)
        if not raw:
            return None
        return self._parse(raw, text, controllable)

    def _parse(
        self, raw: str, text: str, controllable: dict[str, Entity]
    ) -> Intent | None:
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        entity_id = data.get("entity_id")
        command = data.get("command")
        if not entity_id or entity_id not in controllable:
            return None
        if command not in controllable[entity_id].commands:
            return None
        params = data.get("params")
        if not isinstance(params, dict):
            params = {}
        return Intent(
            entity_id=entity_id,
            command=command,
            params=params,
            source="llm",
            raw_text=text,
        )
