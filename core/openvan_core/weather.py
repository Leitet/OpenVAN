"""Weather — location-aware, offline-first.

Fetches the forecast for the van's current GPS position from open-meteo (keyless,
free) and caches it locally, so the last-known forecast is available with no
internet. Cloud enhances; it is never required. Powers "rain expected in an hour"
in the companion, a rain advisor, and the simulator's weather panel.

A synthetic ``simulate()`` path lets the rain behaviour be demoed and tested
offline (Rule 1: works in the simulator).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)

# WMO weather codes -> short condition text.
_WMO = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle",
    55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain",
    67: "Freezing rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow",
    77: "Snow grains", 80: "Rain showers", 81: "Rain showers",
    82: "Violent showers", 85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
}

Location = tuple[float | None, float | None]

_CARDINALS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def _at(seq: list, i: int) -> Any:
    return seq[i] if 0 <= i < len(seq) else None


def _cardinal(deg: float | None) -> str | None:
    """Compass direction the wind is coming FROM, e.g. 350° -> 'N'."""
    if deg is None:
        return None
    return _CARDINALS[int((deg % 360) / 45.0 + 0.5) % 8]


class WeatherService:
    def __init__(
        self,
        config: Any,
        get_location: Callable[[], Location],
        bus: Any = None,
        fetcher: Callable[[float, float], Awaitable[dict | None]] | None = None,
    ) -> None:
        self.config = config
        self.get_location = get_location
        self.bus = bus
        self._fetcher = fetcher or self._fetch_open_meteo
        self._snapshot: dict[str, Any] | None = None
        self._task: asyncio.Task | None = None

    # --- lifecycle -------------------------------------------------------
    async def start(self) -> None:
        self._load_cache()
        await self.refresh()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.config.weather_refresh_s)
            await self.refresh()

    # --- data ------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        return self._snapshot or {}

    def rain_eta_hours(self) -> float | None:
        if self._snapshot is None:
            return None
        return self._snapshot.get("rain_eta_hours")

    async def refresh(self) -> None:
        lat, lon = self.get_location()
        if lat is None or lon is None:
            return
        raw = await self._fetcher(float(lat), float(lon))
        if raw is None:
            if self._snapshot is not None:
                self._snapshot["online"] = False
            return
        await self._set(self._parse(raw, (lat, lon)))
        self._save_cache()

    async def simulate(self, scenario: str = "rain") -> dict[str, Any]:
        """Inject a synthetic forecast (for offline demos / tests)."""
        base = datetime.now().replace(minute=0, second=0, microsecond=0)
        raining = scenario == "rain"
        hourly = []
        for i in range(24):
            wet = raining and 1 <= i <= 4
            hourly.append(
                {
                    "t": (base + timedelta(hours=i)).isoformat(timespec="minutes"),
                    "temp_c": round(12.0 - 0.2 * i, 1),
                    "precip_mm": 1.4 if wet else 0.0,
                    "precip_prob": 85 if wet else 5,
                    "cloud_pct": 90 if wet else 20,
                }
            )
        lat, lon = self.get_location()
        snap = {
            "source": "simulated",
            "online": False,
            "updated_at": time.time(),
            "location": {"lat": lat, "lon": lon},
            "current": {
                "temp_c": 12.0,
                "precip_mm": 0.0,
                "cloud_pct": 60 if raining else 10,
                "wind_kmh": 6.0,
                "code": 3 if raining else 0,
                "condition": "Overcast" if raining else "Clear",
            },
            "hourly": hourly,
            "rain_eta_hours": 1.0 if raining else None,
        }
        await self._set(snap)
        return snap

    async def _set(self, snapshot: dict[str, Any]) -> None:
        self._snapshot = snapshot
        if self.bus is not None:
            await self.bus.publish("weather.updated", {"weather": snapshot})

    # --- open-meteo ------------------------------------------------------
    async def _fetch_open_meteo(self, lat: float, lon: float) -> dict | None:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,precipitation,cloud_cover,weather_code,wind_speed_10m,wind_direction_10m",
            "hourly": "temperature_2m,precipitation,precipitation_probability,cloud_cover",
            "wind_speed_unit": "kmh",
            "forecast_days": 2,
            "timezone": "auto",
        }
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(self.config.weather_base_url, params=params)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.warning("weather fetch failed: %r", exc)
            return None

    def _parse(self, raw: dict, loc: Location) -> dict[str, Any]:
        cur = raw.get("current", {}) or {}
        hourly_raw = raw.get("hourly", {}) or {}
        times = hourly_raw.get("time", []) or []
        temps = hourly_raw.get("temperature_2m", []) or []
        precs = hourly_raw.get("precipitation", []) or []
        probs = hourly_raw.get("precipitation_probability", []) or []
        clouds = hourly_raw.get("cloud_cover", []) or []

        cur_time = cur.get("time", "")
        start = 0
        for i, t in enumerate(times):
            if t >= cur_time:
                start = i
                break

        hourly = []
        for i in range(start, min(start + 24, len(times))):
            hourly.append(
                {
                    "t": times[i],
                    "temp_c": _at(temps, i),
                    "precip_mm": _at(precs, i),
                    "precip_prob": _at(probs, i),
                    "cloud_pct": _at(clouds, i),
                }
            )

        eta: float | None = None
        if (cur.get("precipitation") or 0) > 0:
            eta = 0.0
        else:
            for j, h in enumerate(hourly):
                if (h["precip_prob"] or 0) >= 50 or (h["precip_mm"] or 0) >= 0.2:
                    eta = float(j)
                    break

        code = cur.get("weather_code")
        return {
            "source": "live",
            "online": True,
            "updated_at": time.time(),
            "location": {"lat": loc[0], "lon": loc[1]},
            "current": {
                "temp_c": cur.get("temperature_2m"),
                "precip_mm": cur.get("precipitation"),
                "cloud_pct": cur.get("cloud_cover"),
                "wind_kmh": cur.get("wind_speed_10m"),
                "wind_dir_deg": cur.get("wind_direction_10m"),
                "wind_from": _cardinal(cur.get("wind_direction_10m")),
                "code": code,
                "condition": _WMO.get(code, "—"),
            },
            "hourly": hourly,
            "rain_eta_hours": eta,
        }

    # --- cache -----------------------------------------------------------
    def _cache_path(self):
        return self.config.data_dir / "weather.json"

    def _load_cache(self) -> None:
        path = self._cache_path()
        if not path.exists():
            return
        try:
            self._snapshot = json.loads(path.read_text())
            self._snapshot["online"] = False  # cached until we refresh
        except (OSError, ValueError):
            logger.warning("could not read weather cache")

    def _save_cache(self) -> None:
        if self._snapshot is None:
            return
        path = self._cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(json.dumps(self._snapshot))
        except OSError:
            logger.warning("could not write weather cache")
