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
