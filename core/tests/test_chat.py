"""The conversational assistant path (Core.chat): commands vs. Q&A."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config


@pytest.fixture
async def core(tmp_path):
    c = build_core(
        Config(
            ai_enabled=False,
            weather_enabled=False,
            memory_enabled=False,
            telemetry_enabled=False,
            data_dir=tmp_path,
        )
    )
    await c.start()
    yield c
    await c.stop()


async def test_chat_runs_a_device_command(core):
    await core.twin.set_signal("house_battery.soc", 80, source="test")
    r = await core.chat("turn on the cabin light")
    assert r["action"] is True
    assert r["ok"] is True
    assert core.hub.entities["light.cabin"].state == "on"


async def test_chat_answers_conversationally_offline(core):
    # Not a command -> a read-only answer, not "could not understand".
    r = await core.chat("what model are you?")
    assert r["action"] is False
    assert r["ok"] is True
    assert "could not understand" not in r["reply"].lower()


class _MemoryLLM:
    """A model that only turns on the heater when the earlier 'freezing' turn is
    present in `history` — proving conversation memory reaches converse()."""

    model = "fake"

    def __init__(self) -> None:
        self.seen_history: list = []

    async def available(self) -> bool:
        return True

    async def chat_json(self, system, user):
        import json

        data = json.loads(user)
        msg = data["message"].lower()
        history = data.get("history", [])
        self.seen_history = history
        if "freezing" in msg:
            return json.dumps({"reply": "I'm sorry — my cabin is cold. Tell me to turn it on."})
        if "turn it on" in msg:
            context = " ".join(h["content"].lower() for h in history)
            if "cold" in context or "freezing" in context:
                return json.dumps(
                    {"action": {"entity_id": "climate.diesel_heater", "command": "turn_on", "params": {}}}
                )
            return json.dumps({"reply": "What would you like me to turn on?"})
        return json.dumps({"reply": "ok"})

    async def chat_text(self, system, user):
        return "ok"


async def test_chat_remembers_context_for_follow_ups(core):
    client = _MemoryLLM()
    core.router._client_factory = lambda _b: client
    core.router._active = True
    await core.twin.set_signal("house_battery.soc", 80, source="test")
    await core.twin.set_signal("diesel_tank.level_pct", 50, source="test")

    first = await core.chat("I am freezing in here")
    assert first["action"] is False  # just a sympathetic reply

    # "Turn it on" alone is ambiguous — it only resolves via the remembered turn.
    second = await core.chat("turn it on")
    assert second["action"] is True
    assert second["ok"] is True
    assert core.hub.entities["climate.diesel_heater"].state != "off"  # heater came on
    # The earlier user message was actually handed to the model as history.
    assert any("freezing" in h["content"].lower() for h in client.seen_history)
