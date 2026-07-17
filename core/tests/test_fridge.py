"""Fridge sensors + warm/door advisors."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.notices import FridgeDoorOpen, FridgeWarm


@pytest.fixture
async def core(tmp_path):
    c = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, data_dir=tmp_path)
    )
    await c.start()
    yield c
    await c.stop()


async def test_fridge_sensors_registered(core):
    await core.twin.set_signal("fridge.temp_c", 3.0, source="test")
    assert core.hub.entities["sensor.fridge_temp"].state == 3.0
    assert core.hub.entities["binary_sensor.fridge_door"].domain == "binary_sensor"


async def test_fridge_warm_advisor(core):
    await core.twin.set_signal("fridge.temp_c", 4.0)
    assert FridgeWarm().evaluate(core.hub) is None
    await core.twin.set_signal("fridge.temp_c", 11.0)
    n = FridgeWarm().evaluate(core.hub)
    assert n is not None and n.level == "warning"


async def test_fridge_door_advisor(core):
    assert FridgeDoorOpen().evaluate(core.hub) is None
    await core.twin.set_signal("fridge.door_open", True)
    assert FridgeDoorOpen().evaluate(core.hub) is not None
    keys = {x["key"] for x in core.advisors.active_notices()}
    assert "fridge_door_open" in keys
