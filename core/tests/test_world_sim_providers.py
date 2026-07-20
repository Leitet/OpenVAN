"""Everything is an integration: the reference van's data comes from removable
world-sim provider cards. Remove one → its domain honestly reads unknown; a real
integration can take the domain over (per-domain mixed mode)."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config


@pytest.fixture
async def core(tmp_path):
    c = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, data_dir=tmp_path)
    )
    await c.start()
    yield c
    await c.stop()


async def test_providers_installed_and_seeding_by_default(core):
    installed = {r["id"] for r in core.integrations_list() if r["installed"]}
    assert {"simulated_van", "sim_energy", "sim_water", "sim_climate", "sim_vehicle"} <= installed
    # Their seeds are the world the UI shows.
    assert core.twin.get("house_battery.soc") == 82.0
    assert core.twin.get("cassette.level_pct") == 20.0
    assert core.twin.get("gps.lat") == 46.5405
    assert core.hub.entities["sensor.house_battery_soc"].state == 82.0


async def test_removing_a_provider_releases_its_domain(core):
    assert await core.set_integration_enabled("sim_energy", False) is True
    # Signals released → unknown, not a frozen fake value.
    assert core.twin.get("house_battery.soc") is None
    assert core.twin.get("solar.power") is None
    assert core.hub.entities["sensor.house_battery_soc"].state is None
    # Other domains are untouched.
    assert core.twin.get("fresh_water.level_pct") == 55.0
    # Re-adding the card seeds it again.
    await core.set_integration_enabled("sim_energy", True)
    assert core.twin.get("house_battery.soc") == 82.0


async def test_provider_does_not_stomp_a_real_source(core):
    """Per-domain mixed mode: a real integration owns the signals it provides."""
    await core.set_integration_enabled("sim_energy", False)
    # A real BMS (or any other source) starts providing the battery.
    await core.twin.set_signal("house_battery.soc", 61.5, source="ble_bms")
    # Installing the sim provider must only fill in the unknowns.
    await core.set_integration_enabled("sim_energy", True)
    assert core.twin.get("house_battery.soc") == 61.5
    assert core.twin.get("solar.power") == 240.0  # was unknown → seeded


async def test_physics_only_evolves_provided_domains(core):
    await core.set_integration_enabled("sim_climate", False)
    assert core.twin.get("cabin.temperature") is None
    # Physics on, thermal domain unprovided → no invented cabin temperature.
    await core.simulation.step(60.0)
    assert core.twin.get("cabin.temperature") is None
    # Provided domains still evolve (the clock always belongs to the world).
    epoch_before = core.twin.get("clock.epoch")
    await core.simulation.step(5.0)
    assert core.twin.get("clock.epoch") != epoch_before
