"""Trip ledger: distance / nights / places / solar composed from the odometer,
the travel journal and telemetry — measured against a resettable start marker."""

from __future__ import annotations

import time

import pytest

from openvan_core import build_core
from openvan_core.config import Config


@pytest.fixture
async def core(tmp_path):
    c = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=True,
               telemetry_enabled=True, simulate=False, data_dir=tmp_path)
    )
    await c.start()
    yield c
    await c.stop()


async def test_start_marker_pinned_on_first_run(core):
    stats = core.trip_stats()
    assert stats["started_at"] is not None
    assert stats["distance_km"] == 0.0  # odometer just started
    assert stats["nights"] == 0


async def test_distance_tracks_odometer_delta(core):
    start_odo = core.twin.get("vehicle.odometer_km")
    await core.twin.set_signal("vehicle.odometer_km", start_odo + 42.5)
    assert core.trip_stats()["distance_km"] == 42.5


async def test_reset_rebases_the_trip(core):
    await core.twin.set_signal("vehicle.odometer_km", core.twin.get("vehicle.odometer_km") + 30.0)
    assert core.trip_stats()["distance_km"] == 30.0
    core.reset_trip()  # start fresh from here
    assert core.trip_stats()["distance_km"] == 0.0
    await core.twin.set_signal("vehicle.odometer_km", core.twin.get("vehicle.odometer_km") + 5.0)
    assert core.trip_stats()["distance_km"] == 5.0


async def test_nights_and_places_from_journal(core):
    # Two named stays logged after the trip start count as nights + places.
    core.memory.bookmark("lake")
    core.memory.set_place("Lago di Braies")
    stats = core.trip_stats()
    assert stats["nights"] >= 1
    assert "Lago di Braies" in stats["places"]


async def test_solar_wh_integrates_pv_power(core):
    # Two telemetry samples of 300 W an hour apart → ~300 Wh. Use timestamps after
    # the startup seed sample and bound the trip window to just those two.
    t0 = time.time() + 10.0
    core.telemetry.record("solar.power", 300.0, t0)
    core.telemetry.record("solar.power", 300.0, t0 + 3600.0)
    core.trip.reset(now=t0)
    wh = core.trip.stats(now=t0 + 3600.0)["solar_wh"]
    assert wh == pytest.approx(300.0, abs=1.0)


async def test_marker_persists_across_restart(core, tmp_path):
    await core.twin.set_signal("vehicle.odometer_km", core.twin.get("vehicle.odometer_km") + 12.0)
    started = core.trip_stats()["started_at"]

    c2 = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=True,
               telemetry_enabled=True, simulate=False, data_dir=tmp_path)
    )
    await c2.start()
    try:
        # Same start marker → the 12 km is still counted (odometer seed is the same).
        assert c2.trip_stats()["started_at"] == started
    finally:
        await c2.stop()


def test_trip_http_surface(tmp_path):
    from fastapi.testclient import TestClient
    from openvan_core.api import build_app

    cfg = Config(ai_enabled=False, weather_enabled=False, memory_enabled=True,
                 telemetry_enabled=True, simulate=False, data_dir=tmp_path)
    with TestClient(build_app(cfg)) as client:
        stats = client.get("/api/trip").json()["trip"]
        assert "distance_km" in stats and "nights" in stats
        reset = client.post("/api/trip/reset").json()["trip"]
        assert reset["distance_km"] == 0.0
