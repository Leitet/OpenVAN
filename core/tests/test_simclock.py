"""Simulated clock: advances time and derives sun / day-night state."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from openvan_core.config import Config
from openvan_core.events import EventBus
from openvan_core.simulation import VanSimulation
from openvan_core.twin import VanTwin


def _epoch(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp()


async def _twin_with(epoch, lat=46.54, lon=11.65, rate=1.0):
    bus = EventBus()
    twin = VanTwin(bus)
    await twin.set_signal("clock.epoch", epoch)
    await twin.set_signal("clock.rate", rate)
    await twin.set_signal("gps.lat", lat)
    await twin.set_signal("gps.lon", lon)
    return twin, VanSimulation(bus, twin)


async def test_clock_advances_by_rate():
    twin, sim = await _twin_with(1000.0, rate=60.0)
    await sim.step(1.0)  # 1 real second × 60 = +60 sim seconds
    assert twin.get("clock.epoch") == pytest.approx(1060.0)


async def test_paused_clock_holds():
    twin, sim = await _twin_with(1000.0, rate=0.0)
    await sim.step(5.0)
    assert twin.get("clock.epoch") == 1000.0


async def test_midday_is_daylight():
    twin, sim = await _twin_with(_epoch(2026, 7, 14, 11))  # ~solar noon in the Alps
    await sim.step(0.0)
    assert twin.get("environment.is_day") is True
    assert twin.get("environment.phase") == "day"
    assert twin.get("sun.elevation_deg") > 30


async def test_midnight_is_night():
    twin, sim = await _twin_with(_epoch(2026, 7, 14, 23))  # ~solar midnight
    await sim.step(0.0)
    assert twin.get("environment.is_day") is False
    assert twin.get("environment.phase") == "night"
    assert twin.get("sun.elevation_deg") < 0


async def test_dawn_dusk_between():
    # Winter so the sun sits low; ~early morning is dawn.
    twin, sim = await _twin_with(_epoch(2026, 1, 15, 6, 30))
    await sim.step(0.0)
    assert twin.get("environment.phase") in ("dawn", "night")


async def test_companion_greeting_follows_sim_clock(tmp_path):
    from openvan_core import build_core

    core = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, data_dir=tmp_path)
    )
    await core.start()
    try:
        # Force the sim clock to morning; the greeting context should read that hour.
        await core.twin.set_signal("clock.epoch", _epoch(2026, 7, 14, 6))  # ~7am local
        ctx = core.companion.build_context(core.hub, [])
        assert ctx["greeting"] == "Good morning"
    finally:
        await core.stop()
