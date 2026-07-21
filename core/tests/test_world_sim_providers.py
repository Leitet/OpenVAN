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


PROVIDERS = [
    "sim_energy", "sim_water", "sim_climate", "sim_vehicle",
    "sim_fridge", "sim_connectivity", "sim_security", "sim_cameras",
]


def _provider_seeds(core, provider_id):
    return core.integrations.get(provider_id).seeds()


async def test_providers_installed_and_seeding_by_default(core):
    installed = {r["id"] for r in core.integrations_list() if r["installed"]}
    assert set(PROVIDERS) | {"simulated_van"} <= installed
    # Their seeds are the world the UI shows.
    assert core.twin.get("house_battery.soc") == 82.0
    assert core.twin.get("cassette.level_pct") == 20.0
    assert core.twin.get("gps.lat") == 46.5405
    assert core.twin.get("fridge.temp_c") == 4.0
    assert core.twin.get("connectivity.signal_pct") == 74.0
    assert core.twin.get("security.door_open") is False
    assert core.twin.get("camera.rear.online") is True
    assert core.hub.entities["sensor.house_battery_soc"].state == 82.0


@pytest.mark.parametrize("provider_id", PROVIDERS)
async def test_every_provider_is_plug_and_play(core, provider_id):
    """The plug-and-play contract, for every card: remove → the whole domain
    reads unknown and nothing crashes; re-add → seeded again."""
    seeds = _provider_seeds(core, provider_id)
    assert seeds, f"{provider_id} has no seeds"
    # Unplug.
    assert await core.set_integration_enabled(provider_id, False) is True
    for key in seeds:
        assert core.twin.get(key) is None, f"{key} not released by {provider_id}"
    # The van keeps running: physics ticks and every advisor evaluates cleanly
    # against the unknowns.
    await core.simulation.step(5.0)
    await core.advisors.evaluate()
    # Replug.
    assert await core.set_integration_enabled(provider_id, True) is True
    for key, value in seeds.items():
        assert core.twin.get(key) == value, f"{key} not reseeded by {provider_id}"


async def test_signal_sources_are_tracked(core):
    """The twin records each signal's last writer — the bench groups its
    auto-generated injectors by data source (plug-and-play for new drivers)."""
    sources = core.twin.sources()
    assert sources["house_battery.soc"] == "sim_energy"
    assert sources["fresh_water.level_pct"] == "sim_water"
    assert sources["cabin_light.on"] == "seed"
    # An injection (bench slider / API) takes over as last writer.
    await core.twin.set_signal("house_battery.soc", 50.0, source="sim")
    assert core.twin.sources()["house_battery.soc"] == "sim"


async def test_world_sim_flag_in_descriptor(core):
    """The UI groups simulated sources apart from hardware via `world_sim`."""
    assert core.integrations.describe("sim_energy")["world_sim"] is True
    assert core.integrations.describe("chinese_heater")["world_sim"] is False
    assert core.integrations.describe("simulated_van")["world_sim"] is False  # master switch


async def test_bare_van_all_providers_removed(core):
    """No providers at all — a real van before any hardware is configured. The
    platform must stay alive and every reading must be honestly unknown."""
    for provider_id in PROVIDERS:
        await core.set_integration_enabled(provider_id, False)
    await core.simulation.step(5.0)
    await core.advisors.evaluate()
    for provider_id in PROVIDERS:
        for key in _provider_seeds(core, provider_id):
            assert core.twin.get(key) is None
    # Nothing pretends: no advisor can fire on unknown data.
    assert core.advisors.active_notices() == []


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
