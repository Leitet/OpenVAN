"""Air-quality & safety advisors: CO, gas, smoke, CO2, condensation, climate."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.notices import (
    CabinClimateExtreme,
    CarbonMonoxide,
    Condensation,
    GasLeak,
    HighCO2,
    Smoke,
    _dew_point_c,
)


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


async def test_air_sensors_registered_and_track_signals(core):
    await core.twin.set_signal("air.co_ppm", 12.0, source="test")
    assert core.hub.entities["sensor.co"].state == 12.0
    assert core.hub.entities["sensor.co2"].unit == "ppm"
    assert core.hub.entities["sensor.cabin_humidity"].category == "safety"


def _co(core):
    return CarbonMonoxide().evaluate(core.hub)


async def test_co_alarm_thresholds(core):
    await core.twin.set_signal("air.co_ppm", 10.0)
    assert _co(core) is None  # background level, fine
    await core.twin.set_signal("air.co_ppm", 40.0)
    n = _co(core)
    assert n is not None and n.level == "warning" and n.data["danger"] is False
    await core.twin.set_signal("air.co_ppm", 120.0)
    n = _co(core)
    assert n.data["danger"] is True
    assert "NOW" in n.message


async def test_gas_leak_and_smoke(core):
    await core.twin.set_signal("air.lpg_pct_lel", 4.0)
    assert GasLeak().evaluate(core.hub) is None
    await core.twin.set_signal("air.lpg_pct_lel", 25.0)
    assert GasLeak().evaluate(core.hub).category == "safety"

    assert Smoke().evaluate(core.hub) is None
    await core.twin.set_signal("air.smoke", True)
    assert Smoke().evaluate(core.hub) is not None


async def test_high_co2_suggests_ventilation(core):
    await core.twin.set_signal("air.co2_ppm", 800.0)
    assert HighCO2().evaluate(core.hub) is None
    await core.twin.set_signal("air.co2_ppm", 1800.0)
    n = HighCO2().evaluate(core.hub)
    assert n is not None and n.level == "suggestion"


def test_dew_point_math():
    # 20°C / 50% RH ≈ 9.3°C dew point (standard reference value).
    assert _dew_point_c(20.0, 50.0) == pytest.approx(9.3, abs=0.4)


async def test_condensation_when_surfaces_hit_dew_point(core):
    # Warm, humid cabin against cold walls → sweating surfaces.
    await core.twin.set_signal("cabin.temperature", 19.0)
    await core.twin.set_signal("cabin.humidity_pct", 75.0)
    await core.twin.set_signal("outside.temperature", 12.0)  # below dew point
    n = Condensation().evaluate(core.hub)
    assert n is not None and "dew point" in n.message.lower()

    # Dry cabin → no risk even on cold walls.
    await core.twin.set_signal("cabin.humidity_pct", 40.0)
    assert Condensation().evaluate(core.hub) is None


async def test_cabin_climate_extreme_only_when_parked(core):
    await core.twin.set_signal("vehicle.ignition", False)
    await core.twin.set_signal("cabin.temperature", 1.0)  # freezing
    n = CabinClimateExtreme().evaluate(core.hub)
    assert n is not None and n.data["kind"] == "cold"

    await core.twin.set_signal("cabin.temperature", 34.0)  # hot
    assert CabinClimateExtreme().evaluate(core.hub).data["kind"] == "hot"

    # Driving → the advisor stays quiet (climate is being managed).
    await core.twin.set_signal("vehicle.ignition", True)
    assert CabinClimateExtreme().evaluate(core.hub) is None


async def test_co_alarm_surfaces_as_a_live_notice(core):
    await core.twin.set_signal("air.co_ppm", 90.0)
    keys = {n["key"] for n in core.advisors.active_notices()}
    assert "carbon_monoxide" in keys
