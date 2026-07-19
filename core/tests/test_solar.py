"""Solar window: the hourly forecast → best-window pick, and the load-timing advisor.
Deterministic, offline — derived only from the weather-aware forecast (Rule 3)."""

from __future__ import annotations

import pytest

from openvan_core.notices import SolarWindow
from openvan_core.predictions import solar_forecast_wh, solar_hourly_forecast, solar_window


def _clear_day(lat: float = 46.5, cloud_pct: int = 10) -> dict:
    """A synthetic clear-ish July day, full 24 h, one forecast entry per hour."""
    hourly = [
        {"t": f"2026-07-14T{h:02d}:00", "cloud_pct": cloud_pct}
        for h in range(24)
    ]
    return {"location": {"lat": lat}, "hourly": hourly}


def test_hourly_forecast_zero_at_night_peaks_midday():
    hrs = solar_hourly_forecast(_clear_day(), capacity_w=600.0)
    by_hour = {h["hour"]: h["watts"] for h in hrs}
    assert by_hour[2] == 0.0 and by_hour[23] == 0.0  # deep night
    # Peak is around solar noon and is a big fraction of capacity on a clear day.
    peak_hour = max(by_hour, key=by_hour.get)
    assert 11 <= peak_hour <= 14
    assert by_hour[peak_hour] > 350.0
    assert by_hour[6] < by_hour[peak_hour]  # morning below the peak


def test_no_forecast_returns_empty_and_none():
    assert solar_hourly_forecast(None, 600.0) == []
    assert solar_hourly_forecast({"location": {"lat": 46.5}}, 600.0) == []  # no hourly
    assert solar_forecast_wh(None, 600.0) is None
    assert solar_window(None, 600.0) is None


def test_forecast_wh_is_the_hourly_integral():
    weather = _clear_day()
    hrs = solar_hourly_forecast(weather, 600.0)
    assert solar_forecast_wh(weather, 600.0) == round(sum(h["watts"] for h in hrs), 0)


def test_solar_window_brackets_the_peak():
    win = solar_window(_clear_day(), capacity_w=600.0)
    assert win is not None
    assert win["start_hour"] < win["peak_hour"] < win["end_hour"]
    assert 6 <= win["start_hour"] <= 12
    assert 13 <= win["end_hour"] <= 20
    assert win["peak_w"] > 350


def test_heavy_cloud_shrinks_the_window_and_peak():
    clear = solar_window(_clear_day(cloud_pct=5), 600.0)
    overcast = solar_window(_clear_day(cloud_pct=95), 600.0)
    assert clear is not None and overcast is not None
    assert overcast["peak_w"] < clear["peak_w"]


# --- advisor -----------------------------------------------------------------

class _FakeWeather:
    def __init__(self, snap):
        self._snap = snap

    def snapshot(self):
        return self._snap


class _FakeTwin:
    def __init__(self, **signals):
        self._signals = signals

    def get(self, key, default=None):
        return self._signals.get(key, default)


class _FakeHub:
    def __init__(self, **signals):
        self.twin = _FakeTwin(**signals)


# 2026-07-14 12:00 UTC — at lon 0 this is local solar hour 12 (inside the day window).
_MIDDAY_EPOCH = 1784030400.0


def test_advisor_suggests_window_when_battery_has_room():
    adv = SolarWindow(_FakeWeather(_clear_day()), 600.0, min_w=200.0, soc_pct=80.0)
    notice = adv.evaluate(_FakeHub(**{"house_battery.soc": 55.0}))
    assert notice is not None
    assert notice.key == "solar_window" and notice.level == "suggestion"
    assert "W" in notice.message and notice.data["window"]["peak_w"] > 200


def test_advisor_quiet_when_battery_full():
    adv = SolarWindow(_FakeWeather(_clear_day()), 600.0, min_w=200.0, soc_pct=80.0)
    assert adv.evaluate(_FakeHub(**{"house_battery.soc": 92.0})) is None


def test_advisor_quiet_when_sun_is_weak():
    # Deep overcast → peak below the min-watts threshold.
    adv = SolarWindow(_FakeWeather(_clear_day(cloud_pct=100)), 300.0, min_w=200.0, soc_pct=80.0)
    assert adv.evaluate(_FakeHub(**{"house_battery.soc": 40.0})) is None


def test_advisor_frames_now_when_clock_is_in_the_window():
    adv = SolarWindow(_FakeWeather(_clear_day()), 600.0, min_w=200.0, soc_pct=80.0)
    # Clock at local midday (in the window) → "right now" framing.
    inside = adv.evaluate(
        _FakeHub(**{"house_battery.soc": 55.0, "clock.epoch": _MIDDAY_EPOCH, "gps.lon": 0.0})
    )
    assert inside is not None
    assert inside.data["now_in_window"] is True
    assert "right now" in inside.message.lower()
    # Clock at 03:00 local (before the window) → "coming later today" framing.
    before = adv.evaluate(
        _FakeHub(
            **{"house_battery.soc": 55.0, "clock.epoch": _MIDDAY_EPOCH - 9 * 3600, "gps.lon": 0.0}
        )
    )
    assert before is not None and before.data["now_in_window"] is False
    assert "around" in before.message.lower()
