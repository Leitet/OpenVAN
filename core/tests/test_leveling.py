"""Leveling: pitch/roll sensors + the 'raise this side N cm' advisor."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.notices import NotLevel, leveling_advice


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


def test_level_van_needs_no_advice():
    assert leveling_advice(0.3, -0.5) is None


def test_roll_right_low_says_raise_right():
    advice = leveling_advice(0.0, 3.0)  # roll>0 = right low
    assert advice["raise_side"] == "right"
    # 3° over a 2 m track ≈ 10 cm.
    assert advice["roll_cm"] == pytest.approx(10, abs=1)
    assert "right" in advice["text"]


def test_pitch_nose_up_says_raise_rear():
    advice = leveling_advice(2.0, 0.0)  # nose up → rear low
    assert advice["raise_end"] == "rear"
    assert advice["raise_side"] is None


async def test_sensors_registered_and_track(core):
    await core.twin.set_signal("imu.roll_deg", 2.5, source="test")
    assert core.hub.entities["sensor.roll"].state == 2.5
    assert core.hub.entities["sensor.pitch"].unit == "°"


async def test_not_level_advisor_only_when_parked(core):
    await core.twin.set_signal("vehicle.ignition", False)
    await core.twin.set_signal("imu.pitch_deg", 0.2)
    await core.twin.set_signal("imu.roll_deg", 3.5)
    n = NotLevel().evaluate(core.hub)
    assert n is not None and n.category == "journey"
    assert "right" in n.message

    # Driving → no leveling nag.
    await core.twin.set_signal("vehicle.ignition", True)
    assert NotLevel().evaluate(core.hub) is None
