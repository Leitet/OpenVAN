"""Routines: user-programmable automations — triggers, guards, waits, ordering —
with every action still passing the safety layer (Rule 2)."""

from __future__ import annotations

import asyncio

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.routines import _minute_crossed, normalize_routine


@pytest.fixture
async def core(tmp_path):
    c = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, data_dir=tmp_path)
    )
    await c.start()
    await c.twin.set_signal("house_battery.soc", 85, source="test")
    await c.twin.set_signal("diesel_tank.level_pct", 60, source="test")
    yield c
    await c.stop()


# --- defaults + compat -------------------------------------------------------

async def test_defaults_are_the_four_scenes(core):
    ids = [r["id"] for r in core.routines.list()]
    assert ids == ["goodnight", "morning", "setup_camp", "leaving"]
    assert all(r["show_on_home"] and r["enabled"] for r in core.routines.list())
    # Scenes-compat home subset keeps the old shape (id/name/icon/description).
    home = core.routines.home_list()
    assert home[0].keys() == {"id", "name", "icon", "description"}


async def test_goodnight_runs_through_safety(core):
    await core.twin.set_signal("cabin_light.on", True)
    res = await core.run_scene("goodnight")
    assert res["ok"] is True
    assert core.hub.entities["light.cabin"].state == "off"
    assert core.hub.entities["climate.diesel_heater"].attributes["setpoint"] == 16
    assert core.hub.entities["switch.water_pump"].state == "off"


async def test_safety_still_blocks_routine_steps(core):
    await core.twin.set_signal("diesel_tank.level_pct", 0.0, source="test")
    res = await core.routines.run("morning")
    blocked = [s for s in res["steps"] if s.get("blocked_by_safety")]
    assert blocked  # heater start refused on an empty tank
    assert core.hub.entities["light.cabin"].state == "on"  # rest still applied


# --- steps: condition / wait / notify ---------------------------------------

async def test_condition_step_stops_the_routine(core):
    await core.routines.save(core.routines.list() + [{
        "id": "warm_if_cold", "name": "Warm if cold",
        "triggers": [{"type": "manual"}],
        "steps": [
            {"type": "condition", "signal": "cabin.temperature", "op": "below", "value": 15},
            {"type": "action", "entity_id": "climate.diesel_heater", "command": "turn_on"},
        ],
    }])
    await core.twin.set_signal("cabin.temperature", 21.0, source="test")
    res = await core.routines.run("warm_if_cold")
    assert res["stopped"] is True
    assert core.hub.entities["climate.diesel_heater"].state == "off"
    # Cold cabin → condition passes → heater starts.
    await core.twin.set_signal("cabin.temperature", 10.0, source="test")
    res = await core.routines.run("warm_if_cold")
    assert res["stopped"] is False
    assert core.hub.entities["climate.diesel_heater"].state == "heating"


async def test_wait_and_notify_steps(core):
    seen = []

    async def on_notify(event):
        seen.append(event.data)

    core.bus.subscribe("routine.notify", on_notify)
    await core.routines.save(core.routines.list() + [{
        "id": "pause_and_tell", "name": "Pause and tell",
        "triggers": [{"type": "manual"}],
        "steps": [
            {"type": "wait", "seconds": 0.01},
            {"type": "notify", "message": "done waiting"},
        ],
    }])
    res = await core.routines.run("pause_and_tell")
    assert [s["ok"] for s in res["steps"]] == [True, True]
    assert seen and seen[0]["message"] == "done waiting"


# --- triggers ----------------------------------------------------------------

async def test_signal_trigger_fires_once_per_crossing(core):
    await core.routines.save(core.routines.list() + [{
        "id": "low_batt", "name": "Battery saver",
        "triggers": [{"type": "signal", "signal": "house_battery.soc",
                      "op": "below", "value": 20}],
        "steps": [{"type": "action", "entity_id": "light.cabin", "command": "turn_off"}],
    }])
    await core.twin.set_signal("cabin_light.on", True)
    await core.hub.set_state("light.cabin", "on")

    await core.twin.set_signal("house_battery.soc", 15.0, source="test")
    await asyncio.sleep(0.05)
    assert core.hub.entities["light.cabin"].state == "off"

    # Still below → no re-fire (light turned back on stays on).
    await core.twin.set_signal("cabin_light.on", True)
    await core.hub.set_state("light.cabin", "on")
    await core.twin.set_signal("house_battery.soc", 14.0, source="test")
    await asyncio.sleep(0.05)
    assert core.hub.entities["light.cabin"].state == "on"

    # Recover above, drop again → fires again.
    await core.twin.set_signal("house_battery.soc", 30.0, source="test")
    await core.twin.set_signal("house_battery.soc", 10.0, source="test")
    await asyncio.sleep(0.05)
    assert core.hub.entities["light.cabin"].state == "off"


async def test_time_trigger_fires_on_clock_crossing(core):
    await core.routines.save(core.routines.list() + [{
        "id": "wake", "name": "Wake",
        "triggers": [{"type": "time", "at": "07:30"}],
        "steps": [{"type": "action", "entity_id": "light.cabin", "command": "turn_on"}],
    }])
    # GPS lon ~11.65 → local ≈ UTC+0.78h. Pick epochs straddling 07:30 local.
    lon = float(core.twin.get("gps.lon"))
    base = 1784000000.0
    local = base + lon / 15.0 * 3600.0
    seconds_into_day = local % 86400
    target = 7 * 3600 + 30 * 60
    before = base + (target - 60) - seconds_into_day
    after = before + 120
    await core.twin.set_signal("clock.epoch", before, source="test")
    await asyncio.sleep(0.02)
    assert core.hub.entities["light.cabin"].state == "off"
    await core.twin.set_signal("clock.epoch", after, source="test")
    await asyncio.sleep(0.05)
    assert core.hub.entities["light.cabin"].state == "on"


def test_minute_crossing_wraps_midnight():
    assert _minute_crossed(100, 105, 103)
    assert not _minute_crossed(100, 105, 106)
    assert _minute_crossed(1438, 2, 0)  # 23:58 → 00:02 crosses midnight
    assert not _minute_crossed(1438, 2, 100)


# --- editing / persistence ---------------------------------------------------

async def test_save_persists_and_survives_restart(core, tmp_path):
    routines = core.routines.list()
    routines[0]["name"] = "Sov gott"
    routines[0]["steps"].append({"type": "notify", "message": "God natt!"})
    await core.routines.save(routines)

    fresh = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, data_dir=tmp_path)
    )
    await fresh.start()
    try:
        saved = fresh.routines.get("goodnight")
        assert saved["name"] == "Sov gott"
        assert saved["steps"][-1] == {"type": "notify", "message": "God natt!"}
    finally:
        await fresh.stop()


async def test_reset_restores_defaults(core):
    await core.routines.save([])
    assert core.routines.list() == []
    await core.routines.reset()
    assert [r["id"] for r in core.routines.list()] == \
        ["goodnight", "morning", "setup_camp", "leaving"]


def test_normalize_drops_junk_and_slugs_ids():
    taken: set[str] = set()
    r = normalize_routine({
        "name": "  My Routine!  ",
        "triggers": [{"type": "bogus"}, {"type": "signal", "signal": "x", "op": "nope"}],
        "steps": [{"type": "wait", "seconds": 99999}, {"type": "mystery"}],
    }, taken)
    assert r["id"] == "my_routine"
    assert r["triggers"] == [{"type": "manual"}]  # nothing valid → manual fallback
    assert r["steps"] == [{"type": "wait", "seconds": 3600.0}]  # clamped


async def test_voice_still_runs_routines(core):
    reply = await core.chat("goodnight")
    assert reply["action"] is True
    assert core.hub.entities["light.cabin"].state == "off"
