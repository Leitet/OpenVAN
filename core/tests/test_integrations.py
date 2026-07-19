"""Integration framework: descriptors, catalog, enable/disable + persistence, and
the sim drivers normalising signals into the twin (Rule 1)."""

from __future__ import annotations

import asyncio
import struct

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


async def test_only_simulator_installed_by_default(core):
    rows = {r["id"]: r for r in core.integrations_list()}
    # The simulator is the one standard/built-in integration; everything else is
    # opt-in from the library.
    assert rows["simulated_van"]["installed"] is True
    assert rows["simulated_van"]["builtin"] is True
    assert rows["victron_venus"]["installed"] is False
    assert rows["victron_venus"]["builtin"] is False
    installed = [r["id"] for r in core.integrations_list() if r["installed"]]
    assert installed == ["simulated_van"]


async def test_builtin_cannot_be_removed(core):
    # A remove request on the built-in simulator is a no-op, not an error.
    assert await core.set_integration_enabled("simulated_van", False) is True
    assert core.integrations.get("simulated_van").enabled is True


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
    # A device-owned reading (ESPHome cabin node) appears once the driver is on.
    await core.set_integration_enabled("esphome", True)
    await core.twin.set_signal("cabin.temperature", 21.0)
    await core.integrations.simulate_all(1.0)
    assert core.twin.get("esphome.cabin_node.temperature") == pytest.approx(20.6)


async def test_disabled_driver_does_not_write(core):
    # RuuviTag is off by default → its device signal stays absent.
    await core.integrations.simulate_all(1.0)
    assert core.twin.get("ruuvitag.outdoor.temperature") is None


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


# --- real transports (Victron) -----------------------------------------------

async def _modbus_server(registers: dict[int, int]):
    """A tiny in-process Modbus-TCP server that answers read-registers requests —
    stands in for a real Cerbo GX so the driver's transport is verifiable offline."""
    async def handle(reader, writer):
        try:
            while True:
                header = await reader.readexactly(7)
                tid, _pid, length, unit = struct.unpack(">HHHB", header)
                _fc, addr, count = struct.unpack(">BHH", await reader.readexactly(length - 1))
                data = b"".join(struct.pack(">H", registers.get(addr + i, 0)) for i in range(count))
                body = bytes([0x03, len(data)]) + data
                writer.write(struct.pack(">HHHB", tid, 0, len(body) + 1, unit) + body)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


async def _wait_for(predicate, timeout=3.0):
    for _ in range(int(timeout / 0.05)):
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


def test_victron_normalisers(core):
    import victron_venus as vv  # discovered onto sys.path by core.start()

    # A raw 840-block read (voltage×100, current×10 signed, SoC, PV W at offset 10).
    block = [1310, 65486, 0, 77, 0, 0, 0, 0, 0, 0, 305]
    assert vv.normalise_registers(block) == {
        "house_battery.voltage": 13.1,
        "house_battery.current": -5.0,
        "house_battery.soc": 77.0,
        "solar.power": 305.0,
    }
    assert vv.normalise_topic("N/x/system/0/Dc/Battery/Soc", b'{"value": 91}') == (
        "house_battery.soc",
        91.0,
    )
    assert vv.normalise_topic("N/x/system/0/Dc/Battery/Soc", b'{"value": null}') is None
    assert vv.normalise_topic("N/x/unrelated/topic", b'{"value": 1}') is None


async def test_victron_modbus_real_path_drives_signals(core):
    # NB: close the server with server.close() only — the driver keeps its poll
    # connection open, so server.wait_closed() would block until teardown.
    server, port = await _modbus_server({840: 1310, 841: 65486, 843: 77, 850: 305})
    try:
        await core.set_integration_enabled("victron_venus", True)
        # Point it at the loopback GX — set_config restarts the transport live.
        await core.set_integration_config(
            "victron_venus",
            {"mode": "modbus_tcp", "host": "127.0.0.1", "port": str(port)},
        )
        got = await _wait_for(lambda: core.twin.get("house_battery.soc") == 77.0)
        assert got, "modbus poll did not update the twin"

        inst = core.integrations.get("victron_venus")
        assert inst.live is True
        assert core.twin.get("house_battery.voltage") == 13.1
        assert core.twin.get("solar.power") == 305.0
        # A live driver owns the signals — the sim fallback must not run.
        row = next(r for r in core.integrations_list() if r["id"] == "victron_venus")
        assert row["mode"] == "modbus_tcp" and row["live"] is True
    finally:
        server.close()


async def test_live_driver_skips_simulation(core):
    # A driver connected to real hardware owns its signals; simulate_all must not
    # also drive its sim path. Force RuuviTag "live" and confirm its device signal
    # is not written by the sim tick.
    await core.set_integration_enabled("ruuvitag", True)
    inst = core.integrations.get("ruuvitag")
    inst.live = True
    await core.twin.set_signal("outside.temperature", 6.0)
    await core.integrations.simulate_all(1.0)
    assert core.twin.get("ruuvitag.outdoor.temperature") is None
    # And once it's no longer live, the sim fallback drives it again.
    inst.live = False
    await core.integrations.simulate_all(1.0)
    assert core.twin.get("ruuvitag.outdoor.temperature") == pytest.approx(6.0)


async def test_unreachable_host_stays_offline(core):
    await core.set_integration_enabled("victron_venus", True)
    # Nothing is listening here → transport can't connect, so it never goes live and
    # the van keeps running on the simulated energy state (offline-first).
    await core.set_integration_config(
        "victron_venus", {"mode": "modbus_tcp", "host": "127.0.0.1", "port": "1"}
    )
    await asyncio.sleep(0.2)
    inst = core.integrations.get("victron_venus")
    assert inst.live is False
    row = next(r for r in core.integrations_list() if r["id"] == "victron_venus")
    assert row["mode"] == "modbus_tcp" and row["live"] is False


def test_integration_config_http(tmp_path):
    cfg = Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
                 telemetry_enabled=False, simulate=False, data_dir=tmp_path)
    with TestClient(build_app(cfg)) as client:
        client.post("/api/integrations", json={"id": "victron_venus", "enabled": True})
        out = client.post(
            "/api/integrations/config",
            json={"id": "victron_venus", "values": {"mode": "modbus_tcp", "host": "10.0.0.5"}},
        )
        assert out.status_code == 200
        row = next(r for r in out.json()["integrations"] if r["id"] == "victron_venus")
        assert row["mode"] == "modbus_tcp"
        host_field = next(f for f in row["config"] if f["key"] == "host")
        assert host_field["value"] == "10.0.0.5"
        assert client.post(
            "/api/integrations/config", json={"id": "nope", "values": {}}
        ).status_code == 404
