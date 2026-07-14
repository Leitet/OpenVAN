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

from .events import EventBus
from .twin import VanTwin


@dataclass
class ThermalParams:
    loss_coeff: float = 0.02  # per second: cabin relaxes toward outside temp
    heat_coeff: float = 0.15  # per second: cabin rises toward setpoint when heating


@dataclass
class WaterParams:
    flow_pct_per_s: float = 0.8  # pump transfer rate, fresh -> grey (% per second)


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
    ) -> None:
        self._bus = bus
        self._twin = twin
        self.interval = interval
        self.thermal = thermal or ThermalParams()
        self.water = water or WaterParams()
        self._task: asyncio.Task | None = None

    async def step(self, dt: float) -> None:
        await self._step_thermal(dt)
        await self._step_water(dt)
        await self._step_vehicle(dt)

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
        if lat is not None and lon is not None:
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
