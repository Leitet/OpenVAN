"""Model router + LLM intent resolver (fake clients — no network, no Ollama)."""

from __future__ import annotations

from openvan_core.config import Config
from openvan_core.entities import Entity
from openvan_core.llm import (
    AnthropicClient,
    LLMIntentResolver,
    ModelRouter,
    OpenAICompatibleClient,
    filter_chat_models,
)


def test_language_directive_names_the_language():
    from openvan_core.llm import language_directive

    assert "Swedish" in language_directive("sv")
    assert "German" in language_directive("de")
    assert "English" in language_directive("xx")  # unknown -> English fallback


def test_filter_chat_models_drops_non_chat():
    ids = [
        "gpt-4o", "gpt-4o-mini", "o3-mini", "text-embedding-3-small",
        "whisper-1", "tts-1", "dall-e-3", "gpt-4o-realtime-preview",
    ]
    assert filter_chat_models(ids) == ["gpt-4o", "gpt-4o-mini", "o3-mini"]


class FakeClient:
    model = "fake"

    def __init__(self, response: str | None = None, available: bool = True) -> None:
        self._response = response
        self._available = available
        self.calls = 0

    async def available(self) -> bool:
        return self._available

    async def chat_json(self, system: str, user: str) -> str | None:
        self.calls += 1
        return self._response

    async def chat_text(self, system: str, user: str) -> str | None:
        return self._response


def _entities() -> dict[str, Entity]:
    return {
        "light.cabin": Entity(
            "light.cabin", "Cabin Light", "light", "lighting",
            controllable=True, commands=["turn_on", "turn_off"],
        ),
        "climate.diesel_heater": Entity(
            "climate.diesel_heater", "Diesel Heater", "climate", "climate",
            controllable=True, commands=["turn_on", "turn_off", "set_temperature"],
        ),
        "sensor.soc": Entity("sensor.soc", "SOC", "sensor", "energy", state=80),
    }


def _resolver(tmp_path, client):
    config = Config(ai_enabled=True, data_dir=tmp_path)
    router = ModelRouter(config, client_factory=lambda _b: client)
    return LLMIntentResolver(router), router


# --- resolver behaviour ------------------------------------------------


async def test_converse_returns_reply_for_a_question(tmp_path):
    client = FakeClient('{"reply": "The battery is at 82%."}', available=True)
    resolver, _ = _resolver(tmp_path, client)
    await resolver.startup()
    intent, reply = await resolver.converse("how is the battery?", _entities(), {"soc": 82})
    assert intent is None
    assert reply == "The battery is at 82%."


async def test_converse_returns_action_for_a_command(tmp_path):
    client = FakeClient(
        '{"action": {"entity_id": "light.cabin", "command": "turn_on"}}', available=True
    )
    resolver, _ = _resolver(tmp_path, client)
    await resolver.startup()
    intent, reply = await resolver.converse("turn on the cabin light", _entities(), {})
    assert reply is None
    assert intent is not None
    assert intent.entity_id == "light.cabin"
    assert intent.command == "turn_on"


async def test_valid_llm_json_becomes_intent(tmp_path):
    resolver, _ = _resolver(
        tmp_path, FakeClient('{"entity_id": "light.cabin", "command": "turn_on"}')
    )
    await resolver.startup()
    intent = await resolver.resolve("some light please", _entities())
    assert intent is not None and intent.entity_id == "light.cabin"
    assert intent.source == "llm"


async def test_invalid_entity_falls_back_to_rules(tmp_path):
    resolver, _ = _resolver(
        tmp_path, FakeClient('{"entity_id": "light.nope", "command": "turn_on"}')
    )
    await resolver.startup()
    intent = await resolver.resolve("turn off the cabin light", _entities())
    assert intent is not None and intent.entity_id == "light.cabin"
    assert intent.command == "turn_off" and intent.source == "text"


async def test_inactive_client_skips_llm(tmp_path):
    client = FakeClient('{"entity_id": "light.cabin", "command": "turn_on"}', available=False)
    resolver, router = _resolver(tmp_path, client)
    await resolver.startup()
    assert router.active is False
    intent = await resolver.resolve("turn on the cabin light", _entities())
    assert client.calls == 0
    assert intent.source == "text"


# --- router binding resolution ----------------------------------------


def test_offline_is_the_default_binding(tmp_path):
    config = Config(data_dir=tmp_path)
    binding = ModelRouter(config).effective_binding()
    assert binding.connectivity == "offline"
    assert binding.model == "llama3.2"


def test_online_binding_uses_online_config(tmp_path):
    config = Config(
        data_dir=tmp_path,
        connectivity="online",
        online_provider="openai_compatible",
        online_base_url="https://api.example/v1",
        online_model="gpt-x",
        online_api_key="k",
    )
    binding = ModelRouter(config).effective_binding()
    assert binding.connectivity == "online"
    assert binding.model == "gpt-x"
    assert binding.base_url == "https://api.example/v1"


def test_openai_provider_pins_to_canonical_endpoint(tmp_path):
    # Provider "openai" ignores any configured base_url and uses api.openai.com.
    config = Config(
        data_dir=tmp_path,
        connectivity="online",
        online_provider="openai",
        online_base_url="https://ignored.example/v1",
        online_model="gpt-4o-mini",
        online_api_key="k",
    )
    binding = ModelRouter(config).effective_binding()
    assert binding.base_url == "https://api.openai.com/v1"


def test_online_provider_selects_client(tmp_path):
    openai_cfg = Config(
        data_dir=tmp_path, connectivity="online",
        online_base_url="https://x/v1", online_model="gpt-x",
    )
    openai_client = ModelRouter(openai_cfg).build_client()
    assert isinstance(openai_client, OpenAICompatibleClient)

    claude_cfg = Config(
        data_dir=tmp_path,
        connectivity="online",
        online_provider="anthropic",
        online_model="claude-opus-4-8",
        online_api_key="k",
    )
    claude_client = ModelRouter(claude_cfg).build_client()
    assert isinstance(claude_client, AnthropicClient)
    assert claude_client.base_url == "https://api.anthropic.com"  # default endpoint


async def test_anthropic_client_unavailable_without_key():
    assert await AnthropicClient(None, "claude-opus-4-8").available() is False


async def test_online_unconfigured_gracefully_falls_back_to_offline(tmp_path):
    config = Config(data_dir=tmp_path, connectivity="online", online_base_url="")

    def factory(binding):
        return FakeClient(available=(binding.connectivity == "offline"))

    router = ModelRouter(config, client_factory=factory)
    await router.refresh()
    assert router.active is True
    assert router.binding().connectivity == "offline"
