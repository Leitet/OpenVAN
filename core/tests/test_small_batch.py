"""The 2026-07 small-items batch: cassette advisor (#17), pet mode, coverage
age cap — each exercised against the twin."""

from __future__ import annotations

import time

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.coverage import CoverageMemory, CoverageSpot
from openvan_core.events import EventBus
from openvan_core.notices import CabinClimateExtreme, CassetteFull
from openvan_core.twin import VanTwin


@pytest.fixture
async def core(tmp_path):
    c = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, simulate=False, data_dir=tmp_path)
    )
    await c.start()
    yield c
    await c.stop()


# --- cassette toilet (#17) ---------------------------------------------------

async def test_cassette_entity_and_advisor(core):
    assert core.hub.entities["sensor.cassette_level"].state == 20.0
    assert CassetteFull(85.0).evaluate(core.hub) is None
    await core.twin.set_signal("cassette.level_pct", 92.0)
    keys = {n["key"] for n in core.advisors.active_notices()}
    assert "cassette_full" in keys
    await core.twin.set_signal("cassette.level_pct", 30.0)
    assert "cassette_full" not in {n["key"] for n in core.advisors.active_notices()}


# --- pet mode ----------------------------------------------------------------

async def test_pet_mode_tightens_the_climate_band(core):
    # 27°C parked: fine for the default band, dangerous with a pet aboard.
    await core.twin.set_signal("cabin.temperature", 27.0)
    assert CabinClimateExtreme(3.0, 30.0).evaluate(core.hub) is None
    notice = CabinClimateExtreme(3.0, 30.0, pet_mode=True).evaluate(core.hub)
    assert notice is not None and notice.data["pet"] is True
    assert "pet" in notice.message.lower()


async def test_pet_mode_via_settings(core):
    await core.twin.set_signal("cabin.temperature", 27.0)
    assert "cabin_climate_extreme" not in {n["key"] for n in core.advisors.active_notices()}
    await core.apply_settings(tuning={"pet_mode": 1})
    await core.advisors.evaluate()
    active = {n["key"]: n for n in {n["key"]: n for n in core.advisors.active_notices()}.values()}
    assert "cabin_climate_extreme" in active


# --- coverage age cap --------------------------------------------------------

async def test_old_coverage_spots_are_not_offered():
    bus = EventBus()
    twin = VanTwin(bus)
    cov = CoverageMemory(bus, twin, max_age_s=3600.0)
    # A strong spot recorded "seven hours ago" ~500 m north of here.
    cov._samples.append(CoverageSpot(46.5450, 11.6550, 90.0, ts=time.time() - 7 * 3600))
    assert cov.best_nearby(46.5400, 11.6550, better_than=5.0) is None
    # The same spot recorded recently IS offered.
    cov._samples.append(CoverageSpot(46.5450, 11.6550, 90.0, ts=time.time() - 60))
    hit = cov.best_nearby(46.5400, 11.6550, better_than=5.0)
    assert hit is not None and hit.spot.signal_pct == 90.0
