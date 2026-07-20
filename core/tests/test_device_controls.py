"""Safety-checked device controls: an integration's controllable devices become
switch entities whose commands run intent → safety → send_command → device (twin
in sim, the transport when live) — never a bare write (Rule 2)."""

from __future__ import annotations

import asyncio

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.intents import Intent


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


# --- sim controls (Rule 1: the whole path works with no hardware) ------------

async def test_sim_relay_registered_as_controllable_switch(core):
    await core.set_integration_enabled("esphome", True)
    entity = core.hub.entities.get("switch.esphome_cabin_node_relay")
    assert entity is not None and entity.controllable
    assert entity.attributes["device_control"] is True
    assert entity.attributes["essential"] is False  # → load-shedding applies
    assert entity.state == "off"


async def test_intent_actuates_the_sim_relay(core):
    await core.set_integration_enabled("esphome", True)
    result = await core.hub.execute_intent(Intent("switch.esphome_cabin_node_relay", "turn_on"))
    assert result.ok
    assert core.twin.get("esphome.cabin_node.relay") is True
    assert core.hub.entities["switch.esphome_cabin_node_relay"].state == "on"


async def test_load_shedding_refuses_the_relay_at_critical_battery(core):
    await core.set_integration_enabled("esphome", True)
    await core.twin.set_signal("house_battery.soc", 5.0)
    result = await core.hub.execute_intent(Intent("switch.esphome_cabin_node_relay", "turn_on"))
    assert not result.ok and result.blocked_by_safety
    assert not core.twin.get("esphome.cabin_node.relay")


async def test_disable_removes_the_control_entity(core):
    await core.set_integration_enabled("esphome", True)
    assert "switch.esphome_cabin_node_relay" in core.hub.entities
    await core.set_integration_enabled("esphome", False)
    assert "switch.esphome_cabin_node_relay" not in core.hub.entities


async def test_control_signal_not_duplicated_as_a_sensor(core):
    await core.set_integration_enabled("esphome", True)
    await core.hub.execute_intent(Intent("switch.esphome_cabin_node_relay", "turn_on"))
    await asyncio.sleep(0.05)
    # device_sensors must not shadow the switch with a read-only sensor.
    assert "sensor.esphome_cabin_node_relay" not in core.hub.entities


# --- the first-party inverter switch ----------------------------------------

async def test_inverter_switch_is_controllable(core):
    result = await core.hub.execute_intent(Intent("switch.inverter", "turn_on"))
    assert result.ok
    assert core.twin.get("inverter.on") is True
    off = await core.hub.execute_intent(Intent("switch.inverter", "turn_off"))
    assert off.ok and core.twin.get("inverter.on") is False


async def test_inverter_load_shed_at_critical_battery(core):
    await core.twin.set_signal("house_battery.soc", 5.0)
    result = await core.hub.execute_intent(Intent("switch.inverter", "turn_on"))
    assert not result.ok and result.blocked_by_safety
    assert not core.twin.get("inverter.on")


# --- real ESPHome node (fake client): commands go over the wire --------------

class _FakeCli:
    def __init__(self):
        self.commands: list[tuple[int, bool]] = []
        self._on_state = None

    async def device_name(self):
        return "Cabin Node"

    async def entity_keys(self):
        return {1: "temperature", 7: "relay"}

    async def switches(self):
        return [{"key": 7, "object_id": "relay", "name": "Awning Relay"}]

    def subscribe_states(self, on_state):
        self._on_state = on_state

    async def switch_command(self, key, state):
        self.commands.append((key, state))
        # A real node echoes the new state back over the API.
        if self._on_state:
            self._on_state(key, state)

    async def disconnect(self):
        pass


async def test_live_node_commands_go_over_the_wire(core):
    fake = _FakeCli()
    inst = core.integrations.get("esphome")

    async def fake_open(host, port, on_stop):
        return fake

    inst._open_client = fake_open
    await core.set_integration_enabled("esphome", True)
    await core.set_integration_config("esphome", {"mode": "native_api", "host": "10.0.0.9"})
    assert await _wait_for(lambda: "switch.esphome_cabin_node_relay" in core.hub.entities)
    entity = core.hub.entities["switch.esphome_cabin_node_relay"]
    assert entity.name == "Awning Relay" and entity.controllable

    result = await core.hub.execute_intent(Intent("switch.esphome_cabin_node_relay", "turn_on"))
    assert result.ok
    # The command went over the native API — and the echo drove the state.
    assert fake.commands == [(7, True)]
    assert await _wait_for(lambda: core.twin.get("esphome.cabin_node.relay") is True)
    assert await _wait_for(
        lambda: core.hub.entities["switch.esphome_cabin_node_relay"].state == "on"
    )


async def test_live_node_commands_still_pass_safety(core):
    fake = _FakeCli()
    inst = core.integrations.get("esphome")
    inst._open_client = lambda host, port, on_stop: _ret(fake)
    await core.set_integration_enabled("esphome", True)
    await core.set_integration_config("esphome", {"mode": "native_api", "host": "10.0.0.9"})
    assert await _wait_for(lambda: "switch.esphome_cabin_node_relay" in core.hub.entities)

    await core.twin.set_signal("house_battery.soc", 5.0)
    result = await core.hub.execute_intent(Intent("switch.esphome_cabin_node_relay", "turn_on"))
    assert not result.ok and result.blocked_by_safety
    assert fake.commands == []  # nothing ever reached the wire


async def _ret(value):
    return value
