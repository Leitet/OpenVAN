"""LLM intent resolver — tested with a fake client (no network, no Ollama)."""

from __future__ import annotations

from openvan_core.entities import Entity
from openvan_core.llm import LLMIntentResolver


class FakeClient:
    model = "fake-model"

    def __init__(self, response: str | None, available: bool = True) -> None:
        self._response = response
        self._available = available
        self.calls = 0

    async def available(self) -> bool:
        return self._available

    async def chat_json(self, system: str, user: str) -> str | None:
        self.calls += 1
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


async def test_valid_llm_json_becomes_intent():
    client = FakeClient('{"entity_id": "light.cabin", "command": "turn_on", "params": {}}')
    resolver = LLMIntentResolver(client)
    await resolver.startup()
    intent = await resolver.resolve("I could use some light", _entities())
    assert intent is not None
    assert intent.entity_id == "light.cabin"
    assert intent.command == "turn_on"
    assert intent.source == "llm"


async def test_set_temperature_with_params():
    client = FakeClient(
        '{"entity_id": "climate.diesel_heater", "command": "set_temperature",'
        ' "params": {"temperature": 21}}'
    )
    resolver = LLMIntentResolver(client)
    await resolver.startup()
    intent = await resolver.resolve("make it 21 degrees", _entities())
    assert intent.command == "set_temperature"
    assert intent.params == {"temperature": 21}


async def test_invalid_entity_falls_back_to_rules():
    # LLM hallucinates a device; the rule-based fallback still handles the text.
    client = FakeClient('{"entity_id": "light.nonexistent", "command": "turn_on"}')
    resolver = LLMIntentResolver(client)
    await resolver.startup()
    intent = await resolver.resolve("turn off the cabin light", _entities())
    assert intent is not None
    assert intent.entity_id == "light.cabin"
    assert intent.command == "turn_off"
    assert intent.source == "text"  # came from the fallback


async def test_garbage_json_falls_back():
    resolver = LLMIntentResolver(FakeClient("not json at all"))
    await resolver.startup()
    intent = await resolver.resolve("turn on the cabin light", _entities())
    assert intent is not None
    assert intent.source == "text"


async def test_inactive_client_skips_llm_entirely():
    client = FakeClient('{"entity_id": "light.cabin", "command": "turn_on"}', available=False)
    resolver = LLMIntentResolver(client)
    await resolver.startup()  # probes -> unavailable
    assert resolver.active is False
    intent = await resolver.resolve("turn on the cabin light", _entities())
    assert client.calls == 0  # never called the LLM
    assert intent.source == "text"


async def test_null_intent_when_nothing_matches():
    resolver = LLMIntentResolver(FakeClient('{"entity_id": null}'))
    await resolver.startup()
    intent = await resolver.resolve("what a lovely day", _entities())
    assert intent is None
