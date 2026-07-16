"""Telemetry-based predictions."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from openvan_core.predictions import compute_predictions, solar_forecast_wh
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


# --- weather-aware solar forecast --------------------------------------


def _weather(cloud_pct: int, start_hour: int = 6, lat: float = 50.0, n: int = 12) -> dict:
    """A synthetic forecast: `n` hours from `start_hour` at a fixed cloud cover."""
    base = datetime(2026, 6, 21, start_hour, 0)  # summer solstice
    hourly = [
        {"t": (base + timedelta(hours=i)).isoformat(timespec="minutes"), "cloud_pct": cloud_pct}
        for i in range(n)
    ]
    return {"location": {"lat": lat, "lon": 10.0}, "hourly": hourly}


def test_solar_clear_beats_overcast_but_overcast_nonzero():
    clear = solar_forecast_wh(_weather(0), 600)
    overcast = solar_forecast_wh(_weather(100), 600)
    assert clear is not None and overcast is not None
    assert clear > overcast > 0  # overcast still yields some diffuse output


def test_solar_night_window_is_zero():
    assert solar_forecast_wh(_weather(0, start_hour=22, n=4), 600) == 0


def test_solar_scales_with_capacity():
    assert solar_forecast_wh(_weather(0), 1200) > solar_forecast_wh(_weather(0), 600)


def test_solar_needs_a_forecast_and_a_panel():
    assert solar_forecast_wh(None, 600) is None
    assert solar_forecast_wh({"hourly": []}, 600) is None
    assert solar_forecast_wh(_weather(0), 0) is None


def test_compute_predictions_adds_forecast_without_telemetry():
    out = compute_predictions(FakeTwin({}), None, weather=_weather(20), solar_capacity_w=600)
    assert out.get("solar_forecast_wh", 0) > 0
