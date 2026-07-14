"""Personality store: built-ins, active selection, fork/edit/delete, persistence."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.personalities import PersonalityStore


@pytest.fixture
async def core(tmp_path):
    c = build_core(Config(ai_enabled=False, weather_enabled=False, memory_enabled=False, data_dir=tmp_path))
    await c.start()
    yield c
    await c.stop()


def test_six_builtins_present(tmp_path):
    store = PersonalityStore(tmp_path / "p.json")
    ids = {p.id for p in store.all()}
    assert {"aurora", "ranger", "scout", "forge", "nomad", "pulse"} == ids
    assert all(p.builtin for p in store.all())


def test_default_active_is_aurora(tmp_path):
    store = PersonalityStore(tmp_path / "p.json")
    assert store.active_id() == "aurora"


def test_fork_creates_editable_copy(tmp_path):
    store = PersonalityStore(tmp_path / "p.json")
    forked = store.fork("pulse", "My Pulse")
    assert forked is not None
    assert forked.builtin is False
    assert forked.based_on == "pulse"
    assert forked.style == store.get("pulse").style  # copied
    # editable now
    updated = store.update(forked.id, tagline="Go.")
    assert updated.tagline == "Go."


def test_builtins_are_read_only(tmp_path):
    store = PersonalityStore(tmp_path / "p.json")
    assert store.update("aurora", tagline="nope") is None
    assert store.delete("aurora") is False


def test_persistence_across_reload(tmp_path):
    path = tmp_path / "p.json"
    store = PersonalityStore(path)
    forked = store.fork("nomad", "Historian")
    store.set_active(forked.id)

    reloaded = PersonalityStore(path)
    assert reloaded.active_id() == forked.id
    assert reloaded.get(forked.id) is not None
    assert reloaded.get(forked.id).based_on == "nomad"


def test_deleting_active_reverts_to_default(tmp_path):
    store = PersonalityStore(tmp_path / "p.json")
    forked = store.fork("scout", "Temp")
    store.set_active(forked.id)
    store.delete(forked.id)
    assert store.active_id() == "aurora"


async def test_active_personality_flows_into_assistant_state(core):
    core.personalities.set_active("ranger")
    assert core.assistant_state()["personality"] == "Ranger"


async def test_briefing_uses_active_persona(core):
    seen = {}

    class FakeClient:
        async def available(self):
            return True

        async def chat_text(self, system, user):
            seen["system"] = system
            return "ok"

    core.personalities.set_active("pulse")
    core.router._client_factory = lambda _b: FakeClient()
    core.router._active = True
    await core.companion.briefing(
        core.hub, [], use_llm=True, persona=core.personalities.get_active().style
    )
    assert "Pulse" in seen["system"]  # active persona injected into the prompt
