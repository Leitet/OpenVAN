"""Coverage memory: the trail of where signal was strong, and the 'better spot
back there' locator that powers the weak-signal advisor's headline hint."""

from __future__ import annotations

import pytest

from openvan_core.coverage import CoverageMemory, compass_point
from openvan_core.events import EventBus
from openvan_core.twin import VanTwin


def test_compass_points():
    assert compass_point(0) == "north"
    assert compass_point(90) == "east"
    assert compass_point(180) == "south"
    assert compass_point(270) == "west"
    assert compass_point(45) == "north-east"


async def _twin() -> tuple[VanTwin, CoverageMemory]:
    bus = EventBus()
    twin = VanTwin(bus)
    cov = CoverageMemory(bus, twin, good_pct=50.0, min_move_m=40.0)
    cov.start()
    return twin, cov


async def _drive_to(twin, lat, lon, signal):
    await twin.set_signal("gps.lat", lat)
    await twin.set_signal("gps.lon", lon)
    await twin.set_signal("connectivity.signal_pct", signal)


async def test_records_trail_only_when_moved():
    twin, cov = await _twin()
    await _drive_to(twin, 46.5400, 11.6550, 85.0)
    await _drive_to(twin, 46.5400, 11.6550, 86.0)  # same spot → no new sample
    assert len(cov._samples) == 1
    await _drive_to(twin, 46.5450, 11.6550, 80.0)  # ~550 m north → new sample
    assert len(cov._samples) == 2


async def test_best_nearby_points_to_strong_spot():
    twin, cov = await _twin()
    # Strong coverage here, then drive ~330 m north into a weak patch.
    await _drive_to(twin, 46.5400, 11.6550, 85.0)
    await _drive_to(twin, 46.5430, 11.6550, 6.0)
    hit = cov.best_nearby(46.5430, 11.6550, better_than=6.0)
    assert hit is not None
    assert hit.spot.signal_pct == 85.0
    assert 250 < hit.distance_m < 400  # ~330 m
    assert hit.direction == "south"  # the strong spot is south of the weak one


async def test_best_nearby_none_when_no_better_spot():
    twin, cov = await _twin()
    await _drive_to(twin, 46.5400, 11.6550, 20.0)  # only ever weak
    await _drive_to(twin, 46.5430, 11.6550, 8.0)
    assert cov.best_nearby(46.5430, 11.6550, better_than=8.0) is None


async def test_far_spot_is_ignored():
    twin, cov = await _twin()
    await _drive_to(twin, 46.5400, 11.6550, 90.0)
    # 5 km away — outside the default 2 km radius.
    assert cov.best_nearby(46.5850, 11.6550, better_than=5.0, within_km=2.0) is None
