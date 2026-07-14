"""Diesel heater plugin behaviour against the simulated van."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.intents import Intent


@pytest.fixture
async def core():
    c = build_core(Config(ai_enabled=False, weather_enabled=False, telemetry_enabled=False))
    await c.start()
    yield c
    await c.stop()


async def test_heater_registers(core):
    entity = core.hub.get_entity("climate.diesel_heater")
    assert entity is not None
    assert entity.controllable
    assert set(entity.commands) == {"turn_on", "turn_off", "set_temperature"}


async def test_turn_on_draws_power_and_heats(core):
    result = await core.hub.execute_intent(Intent("climate.diesel_heater", "turn_on"))
    assert result.ok
    assert core.hub.get_entity("climate.diesel_heater").state == "heating"
    assert core.twin.get("diesel_heater.on") is True
    assert core.twin.get("diesel_heater.power") > 0


async def test_turn_off_stops_draw(core):
    await core.hub.execute_intent(Intent("climate.diesel_heater", "turn_on"))
    await core.hub.execute_intent(Intent("climate.diesel_heater", "turn_off"))
    assert core.twin.get("diesel_heater.power") == 0.0
    assert core.hub.get_entity("climate.diesel_heater").state == "off"


async def test_set_temperature_clamps_and_updates(core):
    await core.hub.execute_intent(
        Intent("climate.diesel_heater", "set_temperature", {"temperature": 99})
    )
    entity = core.hub.get_entity("climate.diesel_heater")
    assert entity.attributes["setpoint"] == 30.0  # clamped to MAX_SETPOINT
    assert core.twin.get("diesel_heater.setpoint") == 30.0


async def test_empty_tank_blocks_start(core):
    await core.twin.set_signal("diesel_tank.level_pct", 0.0)
    result = await core.hub.execute_intent(Intent("climate.diesel_heater", "turn_on"))
    assert not result.ok
    assert result.blocked_by_safety
    assert core.twin.get("diesel_heater.on") is False


async def test_critical_battery_blocks_start(core):
    await core.twin.set_signal("house_battery.soc", 4.0)
    result = await core.hub.execute_intent(Intent("climate.diesel_heater", "turn_on"))
    assert not result.ok
    assert result.blocked_by_safety
