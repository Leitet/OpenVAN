"""Telemetry-based predictions."""

from __future__ import annotations

import pytest

from openvan_core.predictions import compute_predictions
from openvan_core.telemetry import TelemetryStore


class FakeTwin:
    def __init__(self, signals: dict) -> None:
        self._signals = signals

    def get(self, key: str, default=None):
        return self._signals.get(key, default)


def test_battery_and_water_etas(tmp_path):
    store = TelemetryStore(tmp_path / "t.db")
    store.open()
    now = 100_000.0
    # battery: 90% -> 80% over an hour = -10%/h, now at 80 -> empty in 8h
    store.record("house_battery.soc", 90.0, now - 3600)
    store.record("house_battery.soc", 80.0, now)
    # fresh water: 60 -> 50 over an hour = -10%/h -> empty in 5h
    store.record("fresh_water.level_pct", 60.0, now - 3600)
    store.record("fresh_water.level_pct", 50.0, now)

    twin = FakeTwin({"house_battery.soc": 80.0, "fresh_water.level_pct": 50.0})
    p = compute_predictions(twin, store, now=now)

    assert p["battery_empty_hours"] == pytest.approx(8.0)
    assert p["battery_rate_pct_per_hour"] == pytest.approx(-10.0)
    assert p["fresh_water_empty_hours"] == pytest.approx(5.0)
    store.close()


def test_solar_energy_integral(tmp_path):
    store = TelemetryStore(tmp_path / "t.db")
    store.open()
    now = 100_000.0
    # constant 100 W for an hour -> 100 Wh
    store.record("solar.power", 100.0, now - 3600)
    store.record("solar.power", 100.0, now)
    p = compute_predictions(FakeTwin({}), store, now=now)
    assert p["solar_wh_24h"] == pytest.approx(100.0)
    store.close()


def test_no_predictions_without_telemetry(tmp_path):
    assert compute_predictions(FakeTwin({}), None) == {}
