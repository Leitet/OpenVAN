"""The van's DC energy system: environment physics (simulation) + the semantic
entities the energy_system plugin surfaces. These are the world's signals, not any
one integration's — so they exist against the bare twin (Rule 1)."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.events import EventBus
from openvan_core.simulation import VanSimulation
from openvan_core.twin import VanTwin


async def _twin_with(**signals) -> tuple[VanTwin, VanSimulation]:
    bus = EventBus()
    twin = VanTwin(bus)
    for key, value in signals.items():
        await twin.set_signal(key.replace("__", "."), value)
    return twin, VanSimulation(bus, twin)


# --- environment physics -----------------------------------------------------

async def test_solar_yield_accumulates_from_pv_power():
    twin, sim = await _twin_with(solar__power=300.0, solar__yield_today_wh=0.0, clock__epoch=1_000_000.0)
    await sim.step(3600.0)  # one hour at 300 W → ~300 Wh
    assert twin.get("solar.yield_today_wh") == pytest.approx(300.0, abs=1.0)


async def test_solar_yield_resets_at_local_midnight():
    # Just before local midnight (UTC, lon 0), with yield already banked.
    twin, sim = await _twin_with(
        solar__power=0.0, solar__yield_today_wh=1500.0, gps__lon=0.0,
        clock__epoch=86400.0 - 10.0,
    )
    await sim.step(1.0)  # establishes the current day without wiping
    assert twin.get("solar.yield_today_wh") == pytest.approx(1500.0, abs=1.0)
    await sim.step(20.0)  # crosses midnight → new day → reset
    assert twin.get("solar.yield_today_wh") == pytest.approx(0.0, abs=0.1)


async def test_alternator_charges_only_while_driving():
    twin, sim = await _twin_with(vehicle__ignition=True, vehicle__speed_kmh=0.0)
    await sim.step(1.0)
    assert twin.get("alternator.power") == 0.0
    await twin.set_signal("vehicle.speed_kmh", 60.0)
    await sim.step(1.0)
    assert twin.get("alternator.power") == sim.energy.alternator_w


async def test_inverter_temperature_rises_with_load():
    twin, sim = await _twin_with(cabin__temperature=20.0, inverter__on=False, inverter__ac_load=0.0)
    await sim.step(1.0)
    assert twin.get("inverter.temperature") == pytest.approx(20.0)
    await twin.set_signal("inverter.on", True)
    await twin.set_signal("inverter.ac_load", 2000.0)  # full rated load
    await sim.step(1.0)
    assert twin.get("inverter.temperature") == pytest.approx(20.0 + sim.energy.inverter_warm_k)


# --- semantic entities -------------------------------------------------------

@pytest.fixture
async def core(tmp_path):
    c = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, simulate=False, data_dir=tmp_path)
    )
    await c.start()
    yield c
    await c.stop()


async def test_energy_entities_registered(core):
    for eid in (
        "sensor.solar_yield_today", "sensor.alternator_power", "binary_sensor.shore_power",
        "switch.inverter", "sensor.inverter_temperature",
    ):
        assert eid in core.hub.entities, eid
    assert core.hub.entities["sensor.alternator_power"].category == "energy"
    assert core.hub.entities["sensor.solar_yield_today"].unit == "Wh"


async def test_energy_entities_follow_signals(core):
    await core.twin.set_signal("alternator.power", 640.0)
    assert core.hub.entities["sensor.alternator_power"].state == 640.0
    await core.twin.set_signal("shore.connected", True)
    assert core.hub.entities["binary_sensor.shore_power"].state is True
    await core.twin.set_signal("inverter.on", True)
    assert core.hub.entities["switch.inverter"].state is True
