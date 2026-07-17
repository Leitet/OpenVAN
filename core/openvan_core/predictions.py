"""Predictions from telemetry history.

Simple, honest forecasts built on recent trends: how long until the battery,
fresh water or diesel run out (linear extrapolation of the last hour's rate),
when the grey tank fills, and how much solar energy came in over the last day
(integral of power). Plus a weather-aware **solar forecast**: expected Wh over the
next day from the forecast cloud cover and the sun's elevation. Deliberately simple
and clearly labelled — not a precision model. Feeds the API and the companion.
"""

from __future__ import annotations

import math
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from .telemetry import TelemetryStore
    from .twin import VanTwin

_HOUR = 3600.0
_DAY = 86400.0
# How much of clear-sky output heavy cloud strips away (overcast still gives some
# diffuse light). Illustrative — tune against a real panel before shipping.
_CLOUD_LOSS = 0.75


def _num(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _solar_elevation_sin(lat_deg: float, day_of_year: int, solar_hour: float) -> float:
    """sin(sun elevation) — negative at night, ~1 at high noon. Standard formula;
    the forecast's local clock hour is used as solar time (no equation-of-time
    correction — this is a rough forecast, not an ephemeris)."""
    decl = math.radians(23.45) * math.sin(math.radians(360.0 * (284 + day_of_year) / 365.0))
    lat = math.radians(lat_deg)
    hour_angle = math.radians(15.0 * (solar_hour - 12.0))
    return math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(hour_angle)


def solar_forecast_wh(
    weather: dict[str, Any] | None,
    capacity_w: float,
    horizon_hours: int = 24,
) -> float | None:
    """Weather-aware expected solar energy (Wh) over the next ``horizon_hours``.

    For each forecast hour: clear-sky output ≈ ``capacity_w · sin(elevation)``,
    scaled by a cloud factor (heavy cloud ≈ -75%). Night hours contribute 0.
    Returns None if we lack a location or an hourly forecast.
    """
    if not weather or capacity_w <= 0:
        return None
    loc = weather.get("location") or {}
    lat = loc.get("lat")
    hourly = weather.get("hourly") or []
    if lat is None or not hourly:
        return None

    total = 0.0
    for h in hourly[:horizon_hours]:
        try:
            dt = datetime.fromisoformat(h.get("t"))
        except (TypeError, ValueError):
            continue
        elev = _solar_elevation_sin(float(lat), dt.timetuple().tm_yday, dt.hour + 0.5)
        if elev <= 0:
            continue  # night — no generation
        cloud_frac = (_num(h.get("cloud_pct")) or 0.0) / 100.0
        cloud_factor = max(0.1, 1.0 - _CLOUD_LOSS * cloud_frac)
        total += capacity_w * min(1.0, elev) * cloud_factor  # W · 1h = Wh
    return round(total, 0)


def compute_predictions(
    twin: "VanTwin",
    telemetry: "TelemetryStore | None",
    now: float | None = None,
    weather: dict[str, Any] | None = None,
    solar_capacity_w: float = 600.0,
) -> dict[str, Any]:
    now = now if now is not None else time.time()
    out: dict[str, Any] = {}

    # Weather-aware solar forecast — needs the forecast, not telemetry history.
    fc = solar_forecast_wh(weather, solar_capacity_w)
    if fc is not None:
        out["solar_forecast_wh"] = fc

    if telemetry is None:
        return out

    def _hours_to(key: str, current: float | None, target: float, rising: bool):
        # ignore_steps: a refill/dump/manual jump is a discontinuity, not a trend —
        # excluding it stops step-changes producing implausibly short ETAs.
        rate = telemetry.rate_per_hour(key, now - _HOUR, ignore_steps=True)
        if current is None or rate is None:
            return None
        if rising and rate > 0.05:
            return round((target - current) / rate, 1)
        if not rising and rate < -0.05:
            return round((current - target) / (-rate), 1)
        return None

    soc = _num(twin.get("house_battery.soc"))
    battery_rate = telemetry.rate_per_hour("house_battery.soc", now - _HOUR, ignore_steps=True)
    if soc is not None and battery_rate is not None:
        out["battery_soc_pct"] = soc
        out["battery_rate_pct_per_hour"] = round(battery_rate, 2)
    battery_empty = _hours_to("house_battery.soc", soc, 0.0, rising=False)
    if battery_empty is not None:
        out["battery_empty_hours"] = battery_empty

    fresh_empty = _hours_to(
        "fresh_water.level_pct", _num(twin.get("fresh_water.level_pct")), 0.0, rising=False
    )
    if fresh_empty is not None:
        out["fresh_water_empty_hours"] = fresh_empty

    grey_full = _hours_to(
        "grey_water.level_pct", _num(twin.get("grey_water.level_pct")), 100.0, rising=True
    )
    if grey_full is not None:
        out["grey_water_full_hours"] = grey_full

    diesel_empty = _hours_to(
        "diesel_tank.level_pct", _num(twin.get("diesel_tank.level_pct")), 0.0, rising=False
    )
    if diesel_empty is not None:
        out["diesel_empty_hours"] = diesel_empty

    out["solar_wh_24h"] = round(telemetry.integral("solar.power", now - _DAY) / 3600.0, 1)
    return out
