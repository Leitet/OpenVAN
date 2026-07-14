"""End-to-end Core behaviour against the simulated van."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.intents import Intent


@pytest.fixture
async def core():
    c = build_core(Config(ai_enabled=False))
    await c.start()
    yield c
    await c.stop()


async def test_plugins_register_their_entities(core):
    assert "sensor.house_battery_soc" in core.hub.entities
    assert "sensor.solar_power" in core.hub.entities
    assert "light.cabin" in core.hub.entities


async def test_sensor_follows_the_twin(core):
    await core.twin.set_signal("house_battery.soc", 42.0)
    assert core.hub.get_entity("sensor.house_battery_soc").state == 42.0


async def test_turning_on_the_light_drives_the_twin(core):
    result = await core.hub.execute_intent(Intent("light.cabin", "turn_on"))
    assert result.ok
    assert core.hub.get_entity("light.cabin").state == "on"
    assert core.twin.get("cabin_light.on") is True


async def test_safety_blocks_non_essential_load_when_battery_critical(core):
    await core.twin.set_signal("house_battery.soc", 5.0)
    result = await core.hub.execute_intent(Intent("light.cabin", "turn_on"))
    assert not result.ok
    assert result.blocked_by_safety
    # The actuator must not have moved.
    assert core.twin.get("cabin_light.on") is False


async def test_offline_text_intent_resolves_and_runs(core):
    result = await core.hub.execute_text("please turn on the cabin light")
    assert result.ok
    assert core.hub.get_entity("light.cabin").state == "on"


async def test_unknown_entity_is_rejected(core):
    result = await core.hub.execute_intent(Intent("light.does_not_exist", "turn_on"))
    assert not result.ok
    assert not result.blocked_by_safety
