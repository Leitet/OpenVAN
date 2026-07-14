"""Predictions from telemetry history.

Simple, honest forecasts built on recent trends: how long until the battery,
fresh water or diesel run out (linear extrapolation of the last hour's rate),
when the grey tank fills, and how much solar energy came in over the last day
(integral of power). Deliberately conservative — a naive linear model, clearly
labelled — rather than pretending to a weather-aware forecast (that waits on the
weather integration). Feeds both the API and the companion's context.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from .telemetry import TelemetryStore
    from .twin import VanTwin

_HOUR = 3600.0
_DAY = 86400.0


def _num(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def compute_predictions(
    twin: "VanTwin",
    telemetry: "TelemetryStore | None",
    now: float | None = None,
) -> dict[str, Any]:
    now = now if now is not None else time.time()
    out: dict[str, Any] = {}
    if telemetry is None:
        return out

    def _hours_to(key: str, current: float | None, target: float, rising: bool):
        rate = telemetry.rate_per_hour(key, now - _HOUR)  # units per hour
        if current is None or rate is None:
            return None
        if rising and rate > 0.05:
            return round((target - current) / rate, 1)
        if not rising and rate < -0.05:
            return round((current - target) / (-rate), 1)
        return None

    soc = _num(twin.get("house_battery.soc"))
    battery_rate = telemetry.rate_per_hour("house_battery.soc", now - _HOUR)
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
