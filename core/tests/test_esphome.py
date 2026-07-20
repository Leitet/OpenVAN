"""ESPHome integration: signal normalisation + the native-API transport driven
through an injected fake client (the real aioesphomeapi + hardware can't run here,
so the vendor surface is faked; the transport loop and twin wiring are real)."""

from __future__ import annotations

import asyncio

import pytest

from openvan_core import build_core
from openvan_core.config import Config


@pytest.fixture
async def core(tmp_path):
    c = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, simulate=False, data_dir=tmp_path)
    )
    await c.start()
    yield c
    await c.stop()


async def _wait_for(predicate, timeout=3.0):
    for _ in range(int(timeout / 0.05)):
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


# --- pure normalisation ------------------------------------------------------

async def test_signal_and_coerce(core):
    import esphome as ha  # package discovered onto sys.path by core.start()

    assert ha.esphome_signal("Cabin Node", "temperature") == "esphome.cabin_node.temperature"
    assert ha.esphome_signal("fridge-1", "door") == "esphome.fridge_1.door"
    assert ha.coerce(True) is True  # a switch/binary stays boolean
    assert ha.coerce("21.55") == 21.55
    assert ha.coerce("on") == "on"  # non-numeric passes through


# --- native-API transport via a fake client ---------------------------------

class _FakeCli:
    def __init__(self, states):
        self._states = states

    async def device_name(self):
        return "Cabin Node"

    async def entity_keys(self):
        return {1: "temperature", 2: "humidity"}

    async def switches(self):
        return []  # a sensor-only node

    def subscribe_states(self, on_state):
        for key, value in self._states:
            on_state(key, value)

    async def disconnect(self):
        pass


async def test_native_api_streams_states_into_twin(core):
    inst = core.integrations.get("esphome")
    await core.set_integration_enabled("esphome", True)

    async def fake_open(host, port, on_stop):
        assert host == "10.0.0.9" and port == 6053
        return _FakeCli([(1, 21.7), (2, 58.0), (99, 1.0)])  # key 99 is unknown → ignored

    inst._open_client = fake_open
    await core.set_integration_config("esphome", {"mode": "native_api", "host": "10.0.0.9"})

    assert await _wait_for(lambda: core.twin.get("esphome.cabin_node.temperature") == 21.7)
    assert core.twin.get("esphome.cabin_node.humidity") == 58.0
    assert inst.live is True
    row = next(r for r in core.integrations_list() if r["id"] == "esphome")
    assert row["mode"] == "native_api" and row["live"] is True


async def test_missing_library_or_host_falls_back_to_sim(core):
    # native_api with no host → nothing to connect to → stays simulated, and the
    # sim driver still produces the node's signals (offline-first).
    await core.set_integration_enabled("esphome", True)
    await core.set_integration_config("esphome", {"mode": "native_api", "host": ""})
    await asyncio.sleep(0.2)
    inst = core.integrations.get("esphome")
    assert inst.live is False
    await core.integrations.simulate_all(1.0)
    assert core.twin.get("esphome.cabin_node.temperature") is not None


def test_esphome_config_fields_declared(core):
    row = next(r for r in core.integrations_list() if r["id"] == "esphome")
    keys = {f["key"] for f in row["config"]}
    assert {"mode", "host", "port", "password", "encryption_key"} <= keys
    # Credentials are write-only secrets.
    pw = next(f for f in row["config"] if f["key"] == "password")
    assert pw["secret"] is True and "value" not in pw
