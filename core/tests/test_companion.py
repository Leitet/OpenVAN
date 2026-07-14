"""Companion briefing — template (offline) and LLM-phrased paths."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config


class FakeClient:
    model = "fake"

    def __init__(self, text: str | None, available: bool = True) -> None:
        self._text = text
        self._available = available
        self.calls = 0
        self.last_system: str | None = None

    async def available(self) -> bool:
        return self._available

    async def chat_json(self, system, user):  # pragma: no cover - unused here
        return None

    async def chat_text(self, system, user):
        self.calls += 1
        self.last_system = system
        return self._text


def _force_llm(core, text):
    """Make the core's router active and return canned text via a fake client."""
    client = FakeClient(text)
    core.router._client_factory = lambda _b: client
    core.router._active = True
    return client


@pytest.fixture
async def core(tmp_path):
    c = build_core(Config(ai_enabled=False, weather_enabled=False, memory_enabled=False, data_dir=tmp_path))
    await c.start()
    yield c
    await c.stop()


async def test_template_briefing_mentions_notices(core):
    await core.twin.set_signal("fresh_water.level_pct", 8.0)
    text = await core.companion.briefing(
        core.hub, core.advisors.active_notices(), use_llm=False
    )
    assert "°C" in text
    assert "Fresh water" in text


async def test_llm_briefing_used_when_active(core):
    _force_llm(core, "Good morning! All systems are happy.")
    text = await core.companion.briefing(
        core.hub, core.advisors.active_notices(), use_llm=True
    )
    assert text == "Good morning! All systems are happy."


async def test_llm_failure_falls_back_to_template(core):
    client = _force_llm(core, None)  # model returns nothing
    text = await core.companion.briefing(
        core.hub, core.advisors.active_notices(), use_llm=True
    )
    assert client.calls == 1
    assert text  # non-empty template


async def test_context_includes_predictions(core):
    ctx = core.companion.build_context(core.hub, [])
    assert "predictions" in ctx and isinstance(ctx["predictions"], dict)
    # solar energy integral is always computed when telemetry is present
    assert "solar_wh_24h" in ctx["predictions"]


def test_template_starts_with_greeting():
    from openvan_core.companion import Companion

    rendered = Companion(None).render_template({"greeting": "Good morning", "notices": []})
    assert rendered.startswith("Good morning.")
