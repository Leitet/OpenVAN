"""Vehicle plugin + motion simulation + journey advisor."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.events import EventBus
from openvan_core.simulation import VanSimulation
from openvan_core.twin import VanTwin


async def _driving_twin(**overrides):
    bus = EventBus()
    twin = VanTwin(bus)
    base = {
        "vehicle.ignition": True,
        "vehicle.speed_kmh": 100.0,
        "vehicle.heading": 90.0,  # east
        "gps.lat": 46.0,
        "gps.lon": 11.0,
        "vehicle.odometer_km": 1000.0,
        "vehicle.trip_seconds": 0.0,
    }
    base.update(overrides)
    for key, value in base.items():
        await twin.set_signal(key, value)
    return bus, twin


async def test_moves_and_accrues_odometer_when_driving():
    bus, twin = await _driving_twin()
    sim = VanSimulation(bus, twin)
    await sim.step(3600.0)  # one hour at 100 km/h
    assert twin.get("vehicle.odometer_km") == pytest.approx(1100.0, abs=0.01)
    assert twin.get("gps.lon") > 11.0  # moved east
    assert twin.get("gps.lat") == pytest.approx(46.0, abs=1e-4)  # heading east
    assert twin.get("vehicle.trip_seconds") == pytest.approx(3600.0)


async def test_trip_resets_when_stopped():
    bus, twin = await _driving_twin(speed_kmh=0.0, **{"vehicle.trip_seconds": 500.0})
    await twin.set_signal("vehicle.speed_kmh", 0.0)
    sim = VanSimulation(bus, twin)
    await sim.step(1.0)
    assert twin.get("vehicle.trip_seconds") == 0.0


async def test_trip_resets_when_ignition_off():
    bus, twin = await _driving_twin()
    await twin.set_signal("vehicle.trip_seconds", 900.0)
    await twin.set_signal("vehicle.ignition", False)
    sim = VanSimulation(bus, twin)
    await sim.step(1.0)
    assert twin.get("vehicle.trip_seconds") == 0.0


@pytest.fixture
async def core(tmp_path):
    c = build_core(Config(ai_enabled=False, telemetry_enabled=False, data_dir=tmp_path))
    await c.start()
    yield c
    await c.stop()


async def test_vehicle_sensors_register(core):
    for eid in ("sensor.vehicle_speed", "sensor.odometer", "sensor.gps_latitude", "sensor.ignition"):
        assert core.hub.get_entity(eid) is not None


async def test_long_drive_advisor(core):
    assert "long_drive" not in {n["key"] for n in core.advisors.active_notices()}
    await core.twin.set_signal("vehicle.trip_seconds", 8000.0)  # > 2h
    assert "long_drive" in {n["key"] for n in core.advisors.active_notices()}
