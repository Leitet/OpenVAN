"""Propane bottle level sensor + low advisor."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.notices import LowPropane


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


async def test_propane_sensor_registered_and_tracks(core):
    await core.twin.set_signal("propane.level_pct", 42.0, source="test")
    assert core.hub.entities["sensor.propane_level"].state == 42.0
    assert core.hub.entities["sensor.propane_level"].unit == "%"


async def test_low_propane_advisor(core):
    await core.twin.set_signal("propane.level_pct", 50.0)
    assert LowPropane().evaluate(core.hub) is None
    await core.twin.set_signal("propane.level_pct", 12.0)
    n = LowPropane().evaluate(core.hub)
    assert n is not None and n.category == "climate"

    # surfaces as a live notice too
    keys = {x["key"] for x in core.advisors.active_notices()}
    assert "propane_low" in keys
