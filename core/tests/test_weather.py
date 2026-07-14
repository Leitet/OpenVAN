"""Weather service — parsing, rain ETA, offline cache, advisor."""

from __future__ import annotations

import pytest

from openvan_core.config import Config
from openvan_core.notices import RainSoon
from openvan_core.weather import WeatherService

# open-meteo-shaped response: rain arriving 2 hours out.
RAINY = {
    "current": {
        "time": "2026-07-14T12:00",
        "temperature_2m": 14.0,
        "precipitation": 0.0,
        "cloud_cover": 40,
        "weather_code": 3,
        "wind_speed_10m": 9.0,
    },
    "hourly": {
        "time": ["2026-07-14T12:00", "2026-07-14T13:00", "2026-07-14T14:00", "2026-07-14T15:00"],
        "temperature_2m": [14.0, 13.5, 13.0, 12.5],
        "precipitation": [0.0, 0.0, 1.2, 0.8],
        "precipitation_probability": [10, 20, 80, 70],
        "cloud_cover": [40, 60, 95, 90],
    },
}


def _config(tmp_path):
    return Config(data_dir=tmp_path, weather_enabled=True)


def _service(tmp_path, raw):
    async def fetch(_lat, _lon):
        return raw

    return WeatherService(_config(tmp_path), lambda: (46.5, 11.6), fetcher=fetch)


async def test_parses_current_and_rain_eta(tmp_path):
    svc = _service(tmp_path, RAINY)
    await svc.refresh()
    snap = svc.snapshot()
    assert snap["online"] is True
    assert snap["current"]["condition"] == "Overcast"
    assert snap["current"]["temp_c"] == 14.0
    # rain starts at hourly index 2 -> ~2h out
    assert svc.rain_eta_hours() == pytest.approx(2.0)


async def test_offline_keeps_last_forecast(tmp_path):
    svc = _service(tmp_path, RAINY)
    await svc.refresh()  # online
    assert svc.snapshot()["online"] is True

    async def fail(_lat, _lon):
        return None

    svc._fetcher = fail
    await svc.refresh()  # offline
    snap = svc.snapshot()
    assert snap["online"] is False
    assert snap["current"]["temp_c"] == 14.0  # last forecast retained


async def test_cache_persists_across_instances(tmp_path):
    svc = _service(tmp_path, RAINY)
    await svc.refresh()
    # a fresh service loads the cached forecast (offline until it refreshes)
    svc2 = WeatherService(_config(tmp_path), lambda: (46.5, 11.6))
    svc2._load_cache()
    assert svc2.snapshot()["current"]["temp_c"] == 14.0
    assert svc2.snapshot()["online"] is False


async def test_simulate_rain(tmp_path):
    svc = _service(tmp_path, {})
    snap = await svc.simulate("rain")
    assert snap["source"] == "simulated"
    assert svc.rain_eta_hours() == 1.0
    clear = await svc.simulate("clear")
    assert clear["rain_eta_hours"] is None


class _FakeWeather:
    def __init__(self, eta):
        self._eta = eta

    def rain_eta_hours(self):
        return self._eta


def test_rain_advisor_fires_within_threshold():
    advisor = RainSoon(_FakeWeather(1.0))
    notice = advisor.evaluate(hub=None)
    assert notice is not None and notice.key == "rain_soon"

    assert RainSoon(_FakeWeather(5.0)).evaluate(hub=None) is None
    assert RainSoon(_FakeWeather(None)).evaluate(hub=None) is None
