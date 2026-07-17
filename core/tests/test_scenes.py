"""Scenes — safety-checked routine bundles, by API and by voice."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.runtime import _match_scene


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
    # Healthy power + fuel so scenes aren't blocked by safety.
    await c.twin.set_signal("house_battery.soc", 85, source="test")
    await c.twin.set_signal("diesel_tank.level_pct", 60, source="test")
    yield c
    await c.stop()


async def test_goodnight_scene_turns_things_off_and_warms(core):
    await core.twin.set_signal("cabin_light.on", True)
    res = await core.run_scene("goodnight")
    assert res["ok"] is True
    assert core.hub.entities["light.cabin"].state == "off"
    assert core.hub.entities["climate.diesel_heater"].attributes["setpoint"] == 16
    assert core.hub.entities["climate.diesel_heater"].state == "heating"
    assert core.hub.entities["switch.water_pump"].state == "off"


async def test_leaving_scene_switches_everything_off(core):
    await core.twin.set_signal("cabin_light.on", True)
    await core.run_scene("setup_camp")  # turn things on first
    res = await core.run_scene("leaving")
    assert res["ok"] is True
    assert core.hub.entities["light.cabin"].state == "off"
    assert core.hub.entities["climate.diesel_heater"].state == "off"


async def test_unknown_scene_returns_none(core):
    assert await core.run_scene("nope") is None


def test_scene_phrase_matching():
    assert _match_scene("goodnight!") == "goodnight"
    assert _match_scene("ok I'm going to bed") == "goodnight"
    assert _match_scene("good morning") == "morning"
    assert _match_scene("let's set up camp here") == "setup_camp"
    assert _match_scene("we're leaving now") == "leaving"
    # Not a routine — must not fire (it would actuate devices).
    assert _match_scene("how's the battery?") is None
    assert _match_scene("turn on the light") is None


async def test_chat_goodnight_runs_the_scene(core):
    await core.twin.set_signal("cabin_light.on", True)
    r = await core.chat("goodnight")
    assert r["action"] is True
    assert "Goodnight" in r["reply"]
    assert core.hub.entities["light.cabin"].state == "off"


async def test_scene_step_blocked_by_safety_is_reported(core):
    # No diesel → the heater turn_on is blocked by FuelRequiredToStart, but the
    # scene still applies what it safely can (the light) and reports the blocked step.
    await core.twin.set_signal("diesel_tank.level_pct", 0, source="test")
    res = await core.run_scene("setup_camp")
    blocked = [s for s in res["steps"] if s.get("blocked_by_safety")]
    assert blocked  # the heater step was held back
    assert core.hub.entities["light.cabin"].state == "on"  # the light still came on
    assert core.hub.entities["climate.diesel_heater"].state == "off"
