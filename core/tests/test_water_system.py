"""Water system plugin behaviour against the simulated van."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.intents import Intent


@pytest.fixture
async def core():
    c = build_core(Config(ai_enabled=False, telemetry_enabled=False))
    await c.start()
    yield c
    await c.stop()


async def test_tanks_and_pump_register(core):
    assert core.hub.get_entity("sensor.fresh_water_level") is not None
    assert core.hub.get_entity("sensor.grey_water_level") is not None
    pump = core.hub.get_entity("switch.water_pump")
    assert pump is not None and pump.controllable


async def test_tank_sensor_follows_twin(core):
    await core.twin.set_signal("fresh_water.level_pct", 33.0)
    assert core.hub.get_entity("sensor.fresh_water_level").state == 33.0


async def test_pump_runs_when_water_available(core):
    result = await core.hub.execute_intent(Intent("switch.water_pump", "turn_on"))
    assert result.ok
    assert core.twin.get("water_pump.on") is True


async def test_pump_blocked_when_tank_empty(core):
    await core.twin.set_signal("fresh_water.level_pct", 0.0)
    result = await core.hub.execute_intent(Intent("switch.water_pump", "turn_on"))
    assert not result.ok
    assert result.blocked_by_safety
    assert core.twin.get("water_pump.on") is False


async def test_pump_is_essential_so_not_load_shed(core):
    # Critically low battery must NOT block the (essential) water pump.
    await core.twin.set_signal("house_battery.soc", 3.0)
    result = await core.hub.execute_intent(Intent("switch.water_pump", "turn_on"))
    assert result.ok
