"""Environment simulation for the digital twin (simulation mode only).

Real vans have physics: a diesel heater warms the cabin, the cabin bleeds heat to
the outside, running the water pump drains the fresh tank into the grey tank. On
real hardware these values come from sensors; while there is no van, this simple
model makes the twin behave believably so features can be exercised end to end.

It is *environment* physics, not an OpenVan feature, so it lives here in the
simulation layer rather than in a plugin — exactly where ``SimBackend`` lives.

The constants below are illustrative, not measured. Tune them against a real van
later (Sourceful principle: simulators are not reality; measure before shipping).
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .events import EventBus
from .predictions import _solar_elevation_sin
from .twin import VanTwin


@dataclass
class ThermalParams:
    loss_coeff: float = 0.02  # per second: cabin relaxes toward outside temp
    heat_coeff: float = 0.15  # per second: cabin rises toward setpoint when heating


@dataclass
class WaterParams:
    flow_pct_per_s: float = 0.8  # pump transfer rate, fresh -> grey (% per second)


@dataclass
class EnergyParams:
    alternator_w: float = 720.0  # DC-DC charge while the engine runs
    inverter_warm_k: float = 18.0  # °C rise at full rated AC load
    inverter_rated_w: float = 2000.0  # load at which that rise is reached


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


class VanSimulation:
    """Advances the twin's physical state over time.

    Use :meth:`step` directly for deterministic tests, or :meth:`start` to run a
    background loop that ticks every ``interval`` seconds.
    """

    def __init__(
        self,
        bus: EventBus,
        twin: VanTwin,
        *,
        interval: float = 1.0,
        thermal: ThermalParams | None = None,
        water: WaterParams | None = None,
        energy: EnergyParams | None = None,
        roads: Any = None,
        integrations: Any = None,
    ) -> None:
        self._bus = bus
        self._twin = twin
        self.interval = interval
        self.thermal = thermal or ThermalParams()
        self.water = water or WaterParams()
        self.energy = energy or EnergyParams()
        # Local day number the solar-yield accumulator belongs to (resets at midnight).
        self._solar_day: int | None = None
        # Optional RoadNetwork: when present, driving snaps to real roads instead
        # of free dead-reckoning. None (or not yet loaded) → dead reckon (offline).
        self._roads = roads
        # Optional IntegrationManager: enabled integration drivers inject their
        # characteristic raw signals each tick (Rule 1 — every integration runs
        # against the twin). None → no integration signals.
        self._integrations = integrations
        # World physics on/off (mirrors ``Config.simulate``). Off on a real van —
        # sensors own those signals. Per-driver sim ticks continue regardless, so
        # a real van can trial a driver in sim mode next to live hardware.
        self.physics = True
        self._task: asyncio.Task | None = None

    def _provided(self, provider_id: str) -> bool:
        """Whether a world-sim provider card is installed — physics only evolves
        a domain someone *provides*. Without a manager (unit tests driving the
        physics directly), everything is considered provided."""
        if self._integrations is None:
            return True
        instance = self._integrations.get(provider_id)
        return instance is not None and instance.enabled

    async def step(self, dt: float) -> None:
        if self.physics:
            await self._step_clock(dt)
            if self._provided("sim_climate"):
                await self._step_thermal(dt)
            if self._provided("sim_water"):
                await self._step_water(dt)
            if self._provided("sim_vehicle"):
                await self._step_vehicle(dt)
            if self._provided("sim_energy"):
                await self._step_energy(dt)
        # Integrations run last so they normalise from the freshly-evolved state.
        if self._integrations is not None:
            await self._integrations.simulate_all(dt)

    async def _step_clock(self, dt: float) -> None:
        """Advance the simulated clock and derive the sun/day-night state from it and
        the van's location. `clock.rate` is a time multiplier (0 = paused, 60 = a
        minute per second) so you can watch a full day go by on the bench."""
        epoch = _as_float(self._twin.get("clock.epoch"))
        if epoch is None:
            return
        rate = _as_float(self._twin.get("clock.rate"))
        rate = 1.0 if rate is None else rate
        epoch += dt * rate
        await self._twin.set_signal("clock.epoch", round(epoch, 1))
        await self.update_sun(epoch)

    async def update_sun(self, epoch: float) -> None:
        """Set sun elevation + day/night phase from the epoch and GPS. Local solar
        time is approximated from longitude (15° per hour) — no timezone db needed."""
        lat = _as_float(self._twin.get("gps.lat")) or 0.0
        lon = _as_float(self._twin.get("gps.lon")) or 0.0
        utc = datetime.fromtimestamp(epoch, tz=timezone.utc)
        doy = utc.timetuple().tm_yday
        solar_hour = (utc.hour + utc.minute / 60.0 + utc.second / 3600.0 + lon / 15.0) % 24
        s = _solar_elevation_sin(lat, doy, solar_hour)
        elev = math.degrees(math.asin(max(-1.0, min(1.0, s))))
        if s > 0.10:
            phase = "day"
        elif s < -0.10:
            phase = "night"
        else:
            phase = "dawn" if solar_hour < 12 else "dusk"
        await self._twin.set_signal("sun.elevation_deg", round(elev, 1))
        await self._twin.set_signal("environment.is_day", s > 0.0)
        await self._twin.set_signal("environment.phase", phase)

    async def _step_thermal(self, dt: float) -> None:
        cabin = _as_float(self._twin.get("cabin.temperature"))
        outside = _as_float(self._twin.get("outside.temperature"))
        if cabin is None or outside is None:
            return
        cabin += self.thermal.loss_coeff * (outside - cabin) * dt
        if self._twin.get("diesel_heater.on"):
            setpoint = _as_float(self._twin.get("diesel_heater.setpoint"))
            if setpoint is not None and setpoint > cabin:
                cabin += self.thermal.heat_coeff * (setpoint - cabin) * dt
        await self._twin.set_signal("cabin.temperature", round(cabin, 2))

    async def _step_water(self, dt: float) -> None:
        if not self._twin.get("water_pump.on"):
            return
        fresh = _as_float(self._twin.get("fresh_water.level_pct")) or 0.0
        grey = _as_float(self._twin.get("grey_water.level_pct")) or 0.0
        delta = min(self.water.flow_pct_per_s * dt, fresh)
        if delta <= 0:
            return
        await self._twin.set_signal("fresh_water.level_pct", round(max(0.0, fresh - delta), 2))
        await self._twin.set_signal("grey_water.level_pct", round(min(100.0, grey + delta), 2))

    async def _step_energy(self, dt: float) -> None:
        """Evolve the van's DC energy state — the world's, not any integration's:
        solar yield accumulates from PV power (resetting at local midnight), the
        alternator charges while the engine runs, and the inverter warms with load.
        A real van reads these from the BMS / GX; here the environment produces them."""
        # Solar yield today (Wh), reset when the local day rolls over.
        epoch = _as_float(self._twin.get("clock.epoch"))
        lon = _as_float(self._twin.get("gps.lon")) or 0.0
        day = int((epoch + lon / 15.0 * 3600.0) // 86400) if epoch is not None else None
        if day is not None and day != self._solar_day:
            if self._solar_day is not None:  # a real day boundary — start fresh
                await self._twin.set_signal("solar.yield_today_wh", 0.0)
            self._solar_day = day
        power = _as_float(self._twin.get("solar.power")) or 0.0
        yield_wh = (_as_float(self._twin.get("solar.yield_today_wh")) or 0.0) + power * dt / 3600.0
        await self._twin.set_signal("solar.yield_today_wh", round(yield_wh, 1))

        # Alternator: charges hard while the engine runs and the van is moving.
        driving = bool(self._twin.get("vehicle.ignition")) and (_as_float(self._twin.get("vehicle.speed_kmh")) or 0.0) > 0
        await self._twin.set_signal("alternator.power", self.energy.alternator_w if driving else 0.0)

        # Inverter outlet temperature: rises with AC load, relaxes to cabin when off.
        cabin = _as_float(self._twin.get("cabin.temperature")) or 20.0
        if self._twin.get("inverter.on"):
            load = _as_float(self._twin.get("inverter.ac_load")) or 0.0
            temp = cabin + self.energy.inverter_warm_k * min(1.0, load / self.energy.inverter_rated_w)
        else:
            temp = cabin
        await self._twin.set_signal("inverter.temperature", round(temp, 1))

    async def _step_vehicle(self, dt: float) -> None:
        if not self._twin.get("vehicle.ignition"):
            if _as_float(self._twin.get("vehicle.trip_seconds")):
                await self._twin.set_signal("vehicle.trip_seconds", 0.0)
            return
        speed = _as_float(self._twin.get("vehicle.speed_kmh")) or 0.0
        if speed <= 0:
            await self._twin.set_signal("vehicle.trip_seconds", 0.0)
            return

        trip = (_as_float(self._twin.get("vehicle.trip_seconds")) or 0.0) + dt
        await self._twin.set_signal("vehicle.trip_seconds", round(trip, 1))

        distance_km = speed * (dt / 3600.0)
        odo = (_as_float(self._twin.get("vehicle.odometer_km")) or 0.0) + distance_km
        await self._twin.set_signal("vehicle.odometer_km", round(odo, 3))

        lat = _as_float(self._twin.get("gps.lat"))
        lon = _as_float(self._twin.get("gps.lon"))
        heading = _as_float(self._twin.get("vehicle.heading")) or 0.0
        if lat is None or lon is None:
            return

        # Prefer following the real road graph; fall back to free dead-reckoning
        # when no roads are loaded (offline / not yet fetched).
        if self._roads is not None:
            snapped = self._roads.advance(lat, lon, heading, distance_km * 1000.0)
            if snapped is not None:
                nlat, nlon, nheading = snapped
                await self._twin.set_signal("gps.lat", nlat)
                await self._twin.set_signal("gps.lon", nlon)
                # The road decides the heading now — reflect the turn we took (a
                # steering bench re-injects the wheel heading on its own cadence).
                if abs(((nheading - heading + 180) % 360) - 180) > 0.5:
                    await self._twin.set_signal("vehicle.heading", nheading)
                # Surface the tightest height/weight limit on the road ahead (0 =
                # none) so the low-clearance / weight-limit advisors can fire early.
                limit = self._roads.restriction_ahead()
                await self._twin.set_signal("road.max_height_m", limit.get("maxheight") or 0.0)
                await self._twin.set_signal("road.max_weight_t", limit.get("maxweight") or 0.0)
                await self._twin.set_signal("road.max_width_m", limit.get("maxwidth") or 0.0)
                return

        # Dead reckoning: heading 0 = north, 90 = east.
        hr = math.radians(heading)
        dlat = distance_km / 111.0 * math.cos(hr)
        dlon = distance_km / (111.0 * max(0.01, math.cos(math.radians(lat)))) * math.sin(hr)
        await self._twin.set_signal("gps.lat", round(lat + dlat, 6))
        await self._twin.set_signal("gps.lon", round(lon + dlon, 6))

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            await self.step(self.interval)
