"""Telemetry time-series store + recorder."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.telemetry import TelemetryStore


def _store(tmp_path) -> TelemetryStore:
    store = TelemetryStore(tmp_path / "t.db")
    store.open()
    return store


def test_record_and_series(tmp_path):
    store = _store(tmp_path)
    store.record("house_battery.soc", 80.0, 1000.0)
    store.record("house_battery.soc", 78.0, 2000.0)
    store.record("solar.power", 200.0, 1500.0)

    soc = store.series("house_battery.soc", since_ts=0)
    assert [p["v"] for p in soc] == [80.0, 78.0]
    assert store.keys() == ["house_battery.soc", "solar.power"]
    store.close()


def test_booleans_recorded_as_numbers(tmp_path):
    store = _store(tmp_path)
    store.record("cabin_light.on", True, 100.0)
    store.record("cabin_light.on", False, 200.0)
    values = [p["v"] for p in store.series("cabin_light.on", since_ts=0)]
    assert values == [1.0, 0.0]
    store.close()


def test_non_numeric_is_ignored(tmp_path):
    store = _store(tmp_path)
    store.record("gps.fix", "3d", 100.0)  # not numeric -> skipped
    assert store.series("gps.fix", since_ts=0) == []
    store.close()


def test_bucketed_downsampling_averages(tmp_path):
    store = _store(tmp_path)
    # two samples in the same 10s bucket -> averaged to one point
    store.record("cabin.temperature", 20.0, 1000.0)
    store.record("cabin.temperature", 22.0, 1005.0)
    store.record("cabin.temperature", 25.0, 1020.0)
    points = store.series("cabin.temperature", since_ts=0, bucket=10.0)
    assert len(points) == 2
    assert points[0]["v"] == pytest.approx(21.0)
    store.close()


def test_rate_per_hour(tmp_path):
    store = _store(tmp_path)
    store.record("house_battery.soc", 90.0, 0.0)
    store.record("house_battery.soc", 80.0, 3600.0)  # -10% over 1 hour
    assert store.rate_per_hour("house_battery.soc", since_ts=0) == pytest.approx(-10.0)
    store.close()


def test_export_rows(tmp_path):
    store = _store(tmp_path)
    store.record("solar.power", 100.0, 100.0)
    store.record("house_battery.soc", 80.0, 150.0)
    store.record("solar.power", 120.0, 200.0)
    all_rows = store.export(since_ts=0)
    assert len(all_rows) == 3
    solar = store.export(since_ts=0, keys=["solar.power"])
    assert [r[2] for r in solar] == [100.0, 120.0]
    store.close()


def test_prune_drops_old_samples(tmp_path):
    store = _store(tmp_path)
    store.record("solar.power", 100.0, 100.0)
    store.record("solar.power", 200.0, 5000.0)
    removed = store.prune(older_than_ts=1000.0)
    assert removed == 1
    assert [p["v"] for p in store.series("solar.power", since_ts=0)] == [200.0]
    store.close()


def test_rollup_aggregates_into_hourly_buckets(tmp_path):
    store = _store(tmp_path)
    # two samples in hour-bucket 0, one in hour-bucket 1
    store.record("solar.power", 100.0, 100.0)
    store.record("solar.power", 300.0, 200.0)  # same hour -> avg 200
    store.record("solar.power", 500.0, 3700.0)  # next hour
    store.rollup()
    hourly = store.series_agg("solar.power", "hour", since_ts=0)
    assert len(hourly) == 2
    assert hourly[0]["v"] == pytest.approx(200.0)
    assert hourly[0]["min"] == 100.0 and hourly[0]["max"] == 300.0
    assert hourly[1]["v"] == pytest.approx(500.0)
    store.close()


def test_rollups_survive_raw_pruning(tmp_path):
    store = _store(tmp_path)
    store.record("house_battery.soc", 90.0, 100.0)
    store.rollup()
    store.prune(older_than_ts=1e9)  # drop all raw
    assert store.series("house_battery.soc", since_ts=0) == []
    # rollup still holds the history
    assert store.series_agg("house_battery.soc", "hour", since_ts=0)[0]["v"] == 90.0
    store.close()


def test_prune_rollups(tmp_path):
    store = _store(tmp_path)
    store.record("solar.power", 100.0, 100.0)
    store.record("solar.power", 200.0, 90000.0)
    store.rollup()
    store.prune_rollups(older_than_ts=3600.0)
    days = store.series_agg("solar.power", "day", since_ts=0)
    assert len(days) == 1  # only the later day-bucket survives
    store.close()


@pytest.fixture
async def core(tmp_path):
    c = build_core(Config(ai_enabled=False, weather_enabled=False, memory_enabled=False, data_dir=tmp_path))
    await c.start()
    yield c
    await c.stop()


async def test_recorder_captures_twin_changes(core):
    await core.twin.set_signal("house_battery.soc", 55.0)
    await core.twin.set_signal("house_battery.soc", 54.0)
    # to_thread writes are awaited within set_signal's publish, so they're durable.
    points = await __import__("asyncio").to_thread(
        core.telemetry.series, "house_battery.soc", 0.0
    )
    values = [p["v"] for p in points]
    assert 55.0 in values and 54.0 in values
