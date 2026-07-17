"""Integration framework: descriptors, catalog, enable/disable + persistence, and
the sim drivers normalising signals into the twin (Rule 1)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from openvan_core import build_core
from openvan_core.api import build_app
from openvan_core.config import Config
from openvan_core.integrations import (
    Integration,
    IntegrationInfo,
    IntegrationManager,
    Status,
    Transport,
)


@pytest.fixture
async def core(tmp_path):
    c = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, simulate=False, data_dir=tmp_path)
    )
    await c.start()
    yield c
    await c.stop()


async def test_catalog_lists_reference_integrations(core):
    rows = core.integrations_list()
    ids = {r["id"] for r in rows}
    # The launch reference set is discovered.
    assert {"simulated_van", "victron_venus", "esphome", "mqtt_homeassistant",
            "modbus_generic", "ruuvitag", "teltonika_router", "autoterm_heater"} <= ids


async def test_descriptor_is_machine_readable(core):
    victron = next(r for r in core.integrations_list() if r["id"] == "victron_venus")
    assert victron["status"] == Status.NATIVE
    assert Transport.MQTT in victron["transports"]
    assert victron["local"] is True and victron["offline_capable"] is True
    assert victron["safety_class"] == 3
    # Permissions are a nested read/control/configure object.
    assert victron["permissions"]["read"] is True
    assert "enabled" in victron


async def test_simulated_van_on_by_default_others_off(core):
    rows = {r["id"]: r["enabled"] for r in core.integrations_list()}
    assert rows["simulated_van"] is True
    assert rows["victron_venus"] is False


async def test_catalog_sorted_by_priority(core):
    priorities = [r["priority"] for r in core.integrations_list()]
    assert priorities == sorted(priorities)


async def test_enable_persists_and_survives_restart(core, tmp_path):
    assert await core.set_integration_enabled("victron_venus", True) is True
    assert core.integrations.get("victron_venus").enabled is True
    # Persisted to the store namespace.
    assert core.store.get_all(IntegrationManager.NS).get("victron_venus") is True

    # A fresh Core over the same data_dir picks the choice back up.
    c2 = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, simulate=False, data_dir=tmp_path)
    )
    await c2.start()
    try:
        assert c2.integrations.get("victron_venus").enabled is True
    finally:
        await c2.stop()


async def test_unknown_integration_toggle_returns_false(core):
    assert await core.set_integration_enabled("nope", True) is False


async def test_enabled_driver_normalises_signals_into_twin(core):
    await core.set_integration_enabled("victron_venus", True)
    await core.twin.set_signal("solar.power", 300.0)
    # One hour of sim: yields ~300 Wh of solar into the normalised signal.
    await core.integrations.simulate_all(3600.0)
    assert core.twin.get("solar.yield_today_wh") == pytest.approx(300.0, abs=1.0)


async def test_disabled_driver_does_not_write(core):
    # Victron is off by default → its signal stays absent.
    await core.integrations.simulate_all(1.0)
    assert core.twin.get("solar.yield_today_wh") is None


async def test_ruuvitag_tracks_outside_temperature(core):
    await core.set_integration_enabled("ruuvitag", True)
    await core.twin.set_signal("outside.temperature", 6.0)
    await core.integrations.simulate_all(1.0)
    assert core.twin.get("ruuvitag.outdoor.temperature") == pytest.approx(6.0)


async def test_registry_only_registers_with_info():
    # A subclass without an info descriptor must not join the registry.
    from openvan_core.integrations import registered_integrations

    before = len(registered_integrations())

    class _NoInfo(Integration):
        pass

    assert len(registered_integrations()) == before

    class _WithInfo(Integration):
        info = IntegrationInfo(id="_probe", name="Probe", category="sensors")

    assert any(c is _WithInfo for c in registered_integrations())


def test_integrations_http_surface(tmp_path):
    cfg = Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
                 telemetry_enabled=False, simulate=False, data_dir=tmp_path)
    with TestClient(build_app(cfg)) as client:
        rows = client.get("/api/integrations").json()["integrations"]
        assert any(r["id"] == "victron_venus" for r in rows)

        # Enable one over HTTP; the catalog reflects it.
        out = client.post("/api/integrations", json={"id": "victron_venus", "enabled": True})
        assert out.status_code == 200
        got = {r["id"]: r["enabled"] for r in out.json()["integrations"]}
        assert got["victron_venus"] is True

        # Unknown id → 404.
        assert client.post("/api/integrations", json={"id": "nope", "enabled": True}).status_code == 404
