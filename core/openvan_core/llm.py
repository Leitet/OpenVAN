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
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .entities import Entity
from .intents import Intent, IntentResolver

logger = logging.getLogger(__name__)

# The canonical OpenAI endpoint. Provider "openai" pins to this (no base URL to
# configure); "openai_compatible" lets the user point anywhere.
OPENAI_URL = "https://api.openai.com/v1"

# Model ids that a chat assistant can't use (embeddings, audio, image, …). A
# provider's /models lists everything the key can access; we keep only chat-capable
# ones. Heuristic and OpenAI-oriented — an exclusion list so unknown/self-hosted
# chat models still show through.
_NON_CHAT_TOKENS = (
    "embedding", "embed", "whisper", "tts", "audio", "transcribe", "dall-e",
    "dalle", "image", "moderation", "rerank", "realtime", "guard",
)


def filter_chat_models(ids: list[str]) -> list[str]:
    """Drop non-chat model ids (embeddings, audio, image generation, …)."""
    return [m for m in ids if not any(tok in m.lower() for tok in _NON_CHAT_TOKENS)]


LANG_NAMES = {"en": "English", "sv": "Swedish", "de": "German"}


def language_directive(lang: str) -> str:
    """A system-prompt line telling the model which language to reply in — while
    still honouring an explicit one-off request for another language."""
    name = LANG_NAMES.get(lang, "English")
    return (
        f"Respond in {name}. Keep every reply in {name}, UNLESS the traveller "
        f"explicitly asks for a specific other language (for example asking how to "
        f"say or translate something) — then answer that particular request in the "
        f"language they asked for."
    )


def with_language(system: str, lang: str, persona: str | None = None) -> str:
    parts = [system, language_directive(lang)]
    if persona:
        parts.append(f"Voice & personality — speak in character:\n{persona}")
    return "\n\n".join(parts)


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

CHAT_SYSTEM = """\
You are OpenVan, the camper van's in-vehicle assistant. Decide whether the
traveller's message is a request to CONTROL a device, or a QUESTION / chat.

You are given `message`, `devices` (controllable — each lists its `commands`) and
`status` (live readings + notices). Respond with JSON ONLY, exactly one of:

  {"action": {"entity_id": "<id>", "command": "<cmd>", "params": {}}}
      — ONLY for an explicit control request. Use a device + command from `devices`.
        For a setpoint use command "set_temperature", params {"temperature": <°C>}.

  {"reply": "<a short, friendly spoken answer, 1-3 sentences>"}
      — for questions, status checks, chit-chat, or anything that is NOT a direct
        control request. Answer using only facts from `status`; if it isn't there,
        say you don't have it.

Questions like "how's the van?", "what's the battery?", "anything to worry about?",
"what can you do?" are NOT actions — use "reply". When in doubt, use "reply" (never
control a device unless clearly asked). Never invent data. No markdown.
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


class OpenAICompatibleClient:
    """Talks to any OpenAI-compatible chat endpoint (OpenAI, OpenRouter, a proxy…).

    ``base_url`` should point at the API root that serves ``/chat/completions`` and
    ``/models`` (e.g. ``https://api.openai.com/v1``). Model-agnostic and open:
    swap the endpoint, keep the code.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def available(self) -> bool:
        if not self.base_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.base_url}/models", headers=self._headers())
                return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        if not self.base_url:
            return []
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.base_url}/models", headers=self._headers())
                resp.raise_for_status()
                return [m["id"] for m in resp.json().get("data", [])]
        except Exception:
            return []

    async def chat_json(self, system: str, user: str) -> str | None:
        return await self._chat(system, user, json_format=True, temperature=0.0)

    async def chat_text(self, system: str, user: str) -> str | None:
        return await self._chat(system, user, json_format=False, temperature=0.6)

    async def _chat(
        self, system: str, user: str, *, json_format: bool, temperature: float
    ) -> str | None:
        base: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        # Newer/reasoning models (o-series, gpt-5.x, …) reject a custom temperature
        # and sometimes response_format. Try our preferred params, then progressively
        # drop the non-standard ones on a 400 so any model still answers.
        variants: list[dict[str, Any]] = [dict(base, temperature=temperature)]
        if json_format:
            variants[0]["response_format"] = {"type": "json_object"}
            variants.append(dict(base, response_format={"type": "json_object"}))
        variants.append(base)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                for i, payload in enumerate(variants):
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers=self._headers(),
                    )
                    if resp.status_code == 400 and i < len(variants) - 1:
                        continue  # model rejected a param — retry more minimally
                    resp.raise_for_status()
                    choices = resp.json().get("choices", [])
                    return choices[0].get("message", {}).get("content") if choices else None
        except Exception as exc:
            logger.warning("online LLM call failed: %r", exc)
        return None


class AnthropicClient:
    """Anthropic Messages API client.

    Raw httpx (like the other clients) to keep the LLM layer dependency-light and
    uniform across backends — the same reason we don't pull in the OpenAI SDK for
    the OpenAI-compatible client. Talks to POST /v1/messages: system is a
    top-level field, max_tokens is required, and the reply is content[].text.
    """

    API_VERSION = "2023-06-01"

    def __init__(
        self,
        api_key: str | None,
        model: str,
        base_url: str = "https://api.anthropic.com",
        timeout: float = 30.0,
        max_tokens: int = 1024,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or "https://api.anthropic.com").rstrip("/")
        self.timeout = timeout
        self.max_tokens = max_tokens

    def _headers(self) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "anthropic-version": self.API_VERSION,
            "x-api-key": self.api_key or "",
        }

    async def available(self) -> bool:
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.base_url}/v1/models", headers=self._headers())
                return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        if not self.api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.base_url}/v1/models", headers=self._headers())
                resp.raise_for_status()
                return [m["id"] for m in resp.json().get("data", [])]
        except Exception:
            return []

    async def chat_json(self, system: str, user: str) -> str | None:
        # Anthropic has no response_format flag here; the system prompt already
        # demands JSON-only, and the caller parses defensively.
        return await self._message(system, user)

    async def chat_text(self, system: str, user: str) -> str | None:
        return await self._message(system, user)

    async def _message(self, system: str, user: str) -> str | None:
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/messages", json=payload, headers=self._headers()
                )
                resp.raise_for_status()
                for block in resp.json().get("content", []):
                    if block.get("type") == "text":
                        return block.get("text")
                return None
        except Exception as exc:
            logger.warning("Anthropic call failed: %r", exc)
            return None


@dataclass
class ModelBinding:
    connectivity: str  # "online" | "offline"
    model: str
    base_url: str
    api_key: str | None = None


class ModelRouter:
    """Resolves which model client to use from the global connectivity setting.

    Connectivity (local/offline vs cloud/online) is a single global mode — it is
    NOT a property of the personality (personalities are voice only). If the
    selected connectivity isn't configured/reachable, the router gracefully falls
    back to the other connectivity so the assistant keeps working; failing that,
    the offline rule-based resolver takes over.
    """

    def __init__(self, config: Any, client_factory=None) -> None:
        self.config = config
        self._client_factory = client_factory or self._default_factory
        self._active = False
        self._binding: ModelBinding | None = None

    @property
    def active(self) -> bool:
        return self._active

    def binding(self) -> ModelBinding:
        return self._binding or self.effective_binding()

    def _online_base_url(self) -> str:
        """Effective base URL for the online provider. 'openai' pins to the
        canonical endpoint; 'anthropic' uses its own (handled by the client);
        'openai_compatible' uses whatever the user configured."""
        provider = getattr(self.config, "online_provider", "openai")
        if provider == "openai":
            return OPENAI_URL
        if provider == "anthropic":
            return ""
        return self.config.online_base_url

    def _default_binding(self, connectivity: str) -> ModelBinding | None:
        if connectivity == "online":
            provider = getattr(self.config, "online_provider", "openai")
            base = self._online_base_url()
            if provider == "anthropic":
                if not self.config.online_api_key:
                    return None
            elif not base:
                return None
            return ModelBinding(
                "online", self.config.online_model, base, self.config.online_api_key
            )
        return ModelBinding("offline", self.config.llm_model, self.config.llm_base_url, None)

    def effective_binding(self) -> ModelBinding:
        if self.config.connectivity == "online":
            return ModelBinding(
                "online",
                self.config.online_model,
                self._online_base_url(),
                self.config.online_api_key,
            )
        return ModelBinding("offline", self.config.llm_model, self.config.llm_base_url, None)

    def _default_factory(self, binding: ModelBinding) -> LLMClient:
        if binding.connectivity == "online":
            provider = getattr(self.config, "online_provider", "openai")
            if provider == "anthropic":
                # base_url is OpenAI-oriented config; Anthropic uses its own endpoint.
                return AnthropicClient(binding.api_key, binding.model)
            return OpenAICompatibleClient(binding.base_url, binding.model, binding.api_key)
        return OllamaClient(binding.base_url, binding.model)

    def build_client(self, binding: ModelBinding | None = None) -> LLMClient:
        return self._client_factory(binding or self.binding())

    async def refresh(self) -> None:
        preferred = self.effective_binding()
        self._binding = preferred
        if not self.config.ai_enabled:
            self._active = False
            return
        if await self.build_client(preferred).available():
            self._active = True
            logger.info("assistant active (%s / %s)", preferred.connectivity, preferred.model)
            return
        # Graceful fallback to the other connectivity's default.
        other = "offline" if preferred.connectivity == "online" else "online"
        alt = self._default_binding(other)
        if alt is not None and await self.build_client(alt).available():
            self._binding = alt
            self._active = True
            logger.info("assistant active via fallback (%s / %s)", alt.connectivity, alt.model)
            return
        self._active = False
        logger.info("assistant unavailable — using offline rule-based resolver")


class LLMIntentResolver(IntentResolver):
    """Resolve text to an Intent via the routed LLM, falling back to rules."""

    def __init__(self, router: ModelRouter, fallback: IntentResolver | None = None) -> None:
        self.router = router
        self.fallback = fallback or IntentResolver()

    @property
    def active(self) -> bool:
        return self.router.active

    @property
    def model(self) -> str | None:
        return self.router.binding().model if self.router.active else None

    async def startup(self) -> None:
        await self.router.refresh()

    async def resolve(self, text: str, entities: dict[str, Any]) -> Intent | None:
        if self.router.active:
            intent = await self._llm_resolve(self.router.build_client(), text, entities)
            if intent is not None:
                return intent
        return await self.fallback.resolve(text, entities)

    @staticmethod
    def _controllable(entities: dict[str, Entity]) -> dict[str, Entity]:
        return {eid: e for eid, e in entities.items() if e.controllable}

    @staticmethod
    def _devices(controllable: dict[str, Entity]) -> list[dict[str, Any]]:
        return [
            {
                "entity_id": e.entity_id,
                "name": e.name,
                "category": e.category,
                "commands": e.commands,
                "state": e.state,
            }
            for e in controllable.values()
        ]

    async def _llm_resolve(
        self, client: LLMClient, text: str, entities: dict[str, Entity]
    ) -> Intent | None:
        controllable = self._controllable(entities)
        if not controllable:
            return None
        context = [
            {"entity_id": e.entity_id, "name": e.name, "state": e.state, "unit": e.unit}
            for e in entities.values()
            if not e.controllable
        ]
        user = json.dumps(
            {"request": text, "devices": self._devices(controllable), "context": context}
        )
        raw = await client.chat_json(SYSTEM_PROMPT, user)
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return None
        return self._intent_from(data, text, controllable)

    async def converse(
        self,
        text: str,
        entities: dict[str, Entity],
        status: dict[str, Any],
        persona: str | None = None,
        language: str = "en",
    ) -> tuple[Intent | None, str | None]:
        """One LLM call that decides between a device action and a chat reply.
        Returns (intent, None) for a command, (None, reply) for an answer, or
        (None, None) if the model is unavailable/unparseable. This is what keeps a
        *question* from being mistaken for a *command*."""
        if not self.router.active:
            return None, None
        controllable = self._controllable(entities)
        system = with_language(CHAT_SYSTEM, language, persona)
        user = json.dumps(
            {"message": text, "devices": self._devices(controllable), "status": status}
        )
        raw = await self.router.build_client().chat_json(system, user)
        if not raw:
            return None, None
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return None, None
        if not isinstance(data, dict):
            return None, None
        action = data.get("action")
        if isinstance(action, dict):
            intent = self._intent_from(action, text, controllable)
            if intent is not None:
                return intent, None
        reply = data.get("reply")
        if isinstance(reply, str) and reply.strip():
            return None, reply.strip()
        return None, None

    def _intent_from(
        self, data: dict[str, Any], text: str, controllable: dict[str, Entity]
    ) -> Intent | None:
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
