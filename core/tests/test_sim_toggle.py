"""The simulator card is the switch for the environment physics — and pausing it
must NOT stop per-driver sim modes (mixed mode: a real van trials a driver in
sim next to live hardware)."""

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


async def test_simulator_card_pauses_and_resumes_the_physics(core):
    assert core.settings()["simulate"] is True
    assert core.integrations.describe("simulated_van")["sim_engine"] is True

    assert await core.set_integration_enabled("simulated_van", False) is True
    assert core.settings()["simulate"] is False
    d = core.integrations.describe("simulated_van")
    # Paused, not uninstalled — the built-in stays in "Your integrations".
    assert d["installed"] is True and d["builtin"] is True
    assert d["sim_engine"] is False

    # Physics paused: the simulated clock no longer advances on a step.
    epoch = core.twin.get("clock.epoch")
    await core.simulation.step(5.0)
    assert core.twin.get("clock.epoch") == epoch

    # Resume via the same card → the world evolves again.
    assert await core.set_integration_enabled("simulated_van", True) is True
    assert core.settings()["simulate"] is True
    await core.simulation.step(5.0)
    assert core.twin.get("clock.epoch") != epoch


async def test_driver_sim_keeps_ticking_while_physics_is_paused(core):
    """Mixed mode: pause the world, add a driver in sim mode — it still works."""
    await core.set_integration_enabled("simulated_van", False)
    await core.set_integration_enabled("chinese_heater", True)
    await core.twin.set_signal("diesel_heater.on", True)
    await core.simulation.step(1.0)
    assert core.twin.get("cdh.run_state") == 5
    assert core.twin.get("cdh.pump_hz") == 2.8


async def test_settings_toggle_reflects_into_the_card(core):
    """The System settings sim toggle and the card are the same switch."""
    await core.apply_settings(simulate=False)
    assert core.integrations.describe("simulated_van")["sim_engine"] is False
    await core.apply_settings(simulate=True)
    assert core.integrations.describe("simulated_van")["sim_engine"] is True
