"""Runtime settings (Admin UI / API / MCP backend)."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config


@pytest.fixture
async def core():
    c = build_core(Config(ai_enabled=False))
    await c.start()
    yield c
    await c.stop()


async def test_settings_reports_state_and_plugins(core):
    s = core.settings()
    assert s["ai_enabled"] is False
    assert s["llm_active"] is False
    assert s["simulate"] is True
    domains = {p["domain"] for p in s["plugins"]}
    assert {"battery_monitor", "cabin_light", "diesel_heater", "water_system"} <= domains


async def test_change_model_updates_config_and_client(core):
    result = await core.apply_settings(llm_model="llama3.1:8b")
    assert result["llm_model"] == "llama3.1:8b"
    assert core.config.llm_model == "llama3.1:8b"
    assert core.hub.resolver.client.model == "llama3.1:8b"


async def test_toggle_simulation(core):
    assert core.simulation._task is not None
    await core.apply_settings(simulate=False)
    assert core.simulation._task is None
    await core.apply_settings(simulate=True)
    assert core.simulation._task is not None


async def test_settings_changed_event_published(core):
    seen = []

    async def handler(event):
        seen.append(event.data["settings"]["simulate"])

    core.bus.subscribe("settings.changed", handler)
    await core.apply_settings(simulate=False)
    assert seen == [False]
