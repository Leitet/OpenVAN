"""Conversation memory — summary + learned preferences, persisted."""

from __future__ import annotations

import json

import pytest

from openvan_core.conversation import ChatMemory
from openvan_core.store import ConfigStore


class _Router:
    """Minimal router stand-in: active + a client that returns canned JSON."""

    def __init__(self, raw: str | None, active: bool = True) -> None:
        self._raw = raw
        self.active = active
        self.seen_user: str | None = None

    def build_client(self):
        router = self

        class _Client:
            model = "fake"

            async def chat_json(self, system, user):
                router.seen_user = user
                return router._raw

            async def chat_text(self, system, user):
                return router._raw

        return _Client()


def _store(tmp_path):
    s = ConfigStore(tmp_path / "store.db")
    s.open()
    return s


def test_apply_updates_summary_and_preferences(tmp_path):
    mem = ChatMemory(_store(tmp_path), _Router(None))
    changed = mem.apply(
        json.dumps(
            {
                "summary": "Traveller is touring the Dolomites, likes it warm.",
                "preferences": ["likes the cabin around 21°C", "prefers quiet spots"],
            }
        )
    )
    assert changed
    assert "Dolomites" in mem.summary
    assert "likes the cabin around 21°C" in mem.preferences


def test_apply_dedupes_and_caps_preferences(tmp_path):
    mem = ChatMemory(_store(tmp_path), _Router(None), max_preferences=3)
    mem.apply(json.dumps({"preferences": ["a", "a", "b", "c", "d", "e"]}))
    assert mem.preferences == ["a", "b", "c"]  # de-duped and capped


def test_apply_ignores_garbage(tmp_path):
    mem = ChatMemory(_store(tmp_path), _Router(None))
    assert mem.apply(None) is False
    assert mem.apply("not json") is False
    assert mem.preferences == [] and mem.summary == ""


def test_memory_persists_and_reloads(tmp_path):
    store = _store(tmp_path)
    mem = ChatMemory(store, _Router(None))
    mem.apply(json.dumps({"summary": "S", "preferences": ["wakes early"]}))
    # A fresh ChatMemory over the same store restores what was learned.
    mem2 = ChatMemory(store, _Router(None))
    mem2.load()
    assert mem2.summary == "S"
    assert mem2.preferences == ["wakes early"]


def test_clear_wipes_and_persists(tmp_path):
    store = _store(tmp_path)
    mem = ChatMemory(store, _Router(None))
    mem.apply(json.dumps({"summary": "S", "preferences": ["x"]}))
    mem.clear()
    mem2 = ChatMemory(store, _Router(None))
    mem2.load()
    assert mem2.summary == "" and mem2.preferences == []


async def test_consolidation_fires_after_enough_turns(tmp_path):
    raw = json.dumps({"summary": "Likes it warm.", "preferences": ["likes cabin at 21°C"]})
    router = _Router(raw)
    mem = ChatMemory(_store(tmp_path), router, consolidate_every=2)

    mem.record("user", "brr it's cold")
    await mem.maybe_consolidate()
    assert mem.preferences == []  # only 1 user turn — not yet

    mem.record("assistant", "I'll warm us up.")
    mem.record("user", "yeah keep it about 21")
    await mem.maybe_consolidate()  # 2 user turns → consolidate
    assert "likes cabin at 21°C" in mem.preferences
    # the model actually received the recent turns
    assert "cold" in (router.seen_user or "")


async def test_no_consolidation_without_a_model(tmp_path):
    mem = ChatMemory(_store(tmp_path), _Router(None, active=False), consolidate_every=1)
    mem.record("user", "hi")
    await mem.maybe_consolidate()
    assert mem.preferences == [] and mem.summary == ""


def test_context_only_includes_what_exists(tmp_path):
    mem = ChatMemory(_store(tmp_path), _Router(None))
    assert mem.context() == {}
    mem.apply(json.dumps({"summary": "S", "preferences": ["p"]}))
    assert mem.context() == {"summary": "S", "preferences": ["p"]}
