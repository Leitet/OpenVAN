"""Model router + LLM intent resolver (fake clients — no network, no Ollama)."""

from __future__ import annotations

from openvan_core.config import Config
from openvan_core.entities import Entity
from openvan_core.llm import LLMIntentResolver, ModelRouter
from openvan_core.personalities import PersonalityStore


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
    store = PersonalityStore(tmp_path / "p.json")
    router = ModelRouter(config, store, client_factory=lambda _b: client)
    return LLMIntentResolver(router), router


# --- resolver behaviour ------------------------------------------------


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


def test_offline_profile_binding(tmp_path):
    config = Config(data_dir=tmp_path)
    store = PersonalityStore(tmp_path / "p.json")
    store.set_active("scout")  # offline
    binding = ModelRouter(config, store).effective_binding()
    assert binding.connectivity == "offline"
    assert binding.model == "llama3.2"


def test_online_profile_uses_online_config(tmp_path):
    config = Config(
        data_dir=tmp_path,
        online_base_url="https://api.example/v1",
        online_model="gpt-x",
        online_api_key="k",
    )
    store = PersonalityStore(tmp_path / "p.json")
    store.set_active("aurora")  # online
    binding = ModelRouter(config, store).effective_binding()
    assert binding.connectivity == "online"
    assert binding.model == "gpt-x"
    assert binding.base_url == "https://api.example/v1"


def test_profile_model_override(tmp_path):
    config = Config(data_dir=tmp_path)
    store = PersonalityStore(tmp_path / "p.json")
    forked = store.fork("scout", "My Scout")
    store.update(forked.id, model="llama3.1:8b")
    store.set_active(forked.id)
    binding = ModelRouter(config, store).effective_binding()
    assert binding.model == "llama3.1:8b"


async def test_online_unconfigured_gracefully_falls_back_to_offline(tmp_path):
    config = Config(data_dir=tmp_path)  # online not configured
    store = PersonalityStore(tmp_path / "p.json")
    store.set_active("aurora")  # prefers online

    def factory(binding):
        return FakeClient(available=(binding.connectivity == "offline"))

    router = ModelRouter(config, store, client_factory=factory)
    await router.refresh()
    assert router.active is True
    assert router.binding().connectivity == "offline"
