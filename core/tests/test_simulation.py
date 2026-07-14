"""Deterministic tests for the environment simulation (thermal + water)."""

from __future__ import annotations

from openvan_core.events import EventBus
from openvan_core.simulation import VanSimulation
from openvan_core.twin import VanTwin


async def _twin_with(**signals) -> tuple[VanTwin, VanSimulation]:
    bus = EventBus()
    twin = VanTwin(bus)
    for key, value in signals.items():
        await twin.set_signal(key.replace("__", "."), value)
    return twin, VanSimulation(bus, twin)


async def test_cabin_cools_toward_outside_when_heater_off():
    twin, sim = await _twin_with(
        cabin__temperature=20.0, outside__temperature=0.0, diesel_heater__on=False
    )
    await sim.step(1.0)
    cabin = twin.get("cabin.temperature")
    assert cabin < 20.0  # lost heat
    assert cabin > 0.0  # but not instantly


async def test_cabin_warms_toward_setpoint_when_heating():
    twin, sim = await _twin_with(
        cabin__temperature=10.0,
        outside__temperature=0.0,
        diesel_heater__on=True,
        diesel_heater__setpoint=22.0,
    )
    start = twin.get("cabin.temperature")
    for _ in range(60):
        await sim.step(1.0)
    warmed = twin.get("cabin.temperature")
    assert warmed > start
    # Settles below the setpoint because of ongoing heat loss to the cold outside.
    assert 14.0 < warmed < 22.0


async def test_pump_moves_water_fresh_to_grey():
    twin, sim = await _twin_with(
        water_pump__on=True, fresh_water__level_pct=50.0, grey_water__level_pct=10.0
    )
    await sim.step(10.0)
    assert twin.get("fresh_water.level_pct") < 50.0
    assert twin.get("grey_water.level_pct") > 10.0


async def test_pump_off_moves_no_water():
    twin, sim = await _twin_with(
        water_pump__on=False, fresh_water__level_pct=50.0, grey_water__level_pct=10.0
    )
    await sim.step(10.0)
    assert twin.get("fresh_water.level_pct") == 50.0


async def test_fresh_tank_never_goes_negative():
    twin, sim = await _twin_with(
        water_pump__on=True, fresh_water__level_pct=0.3, grey_water__level_pct=99.9
    )
    await sim.step(10.0)
    assert twin.get("fresh_water.level_pct") == 0.0
    assert twin.get("grey_water.level_pct") <= 100.0
