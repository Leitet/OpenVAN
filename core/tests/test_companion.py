"""Companion briefing — template (offline) and LLM-phrased paths."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.companion import Companion
from openvan_core.config import Config


class FakeClient:
    model = "fake"

    def __init__(self, text: str | None) -> None:
        self._text = text
        self.calls = 0

    async def available(self) -> bool:
        return True

    async def chat_json(self, system, user):  # pragma: no cover - unused here
        return None

    async def chat_text(self, system, user):
        self.calls = self.calls + 1
        return self._text


@pytest.fixture
async def core():
    c = build_core(Config(ai_enabled=False))
    await c.start()
    yield c
    await c.stop()


async def test_template_briefing_mentions_notices(core):
    await core.twin.set_signal("fresh_water.level_pct", 8.0)
    companion = Companion(FakeClient(None))
    text = await companion.briefing(core.hub, core.advisors.active_notices(), use_llm=False)
    assert "°C" in text
    assert "Fresh water" in text  # active notice folded into the briefing


async def test_llm_briefing_used_when_available(core):
    companion = Companion(FakeClient("Good morning! All systems are happy."))
    text = await companion.briefing(core.hub, core.advisors.active_notices(), use_llm=True)
    assert text == "Good morning! All systems are happy."


async def test_llm_failure_falls_back_to_template(core):
    client = FakeClient(None)  # model returns nothing
    companion = Companion(client)
    text = await companion.briefing(core.hub, core.advisors.active_notices(), use_llm=True)
    assert client.calls == 1
    assert text  # non-empty template


def test_template_starts_with_greeting():
    companion = Companion(FakeClient(None))
    rendered = companion.render_template({"greeting": "Good morning", "notices": []})
    assert rendered.startswith("Good morning.")
