"""HA/MQTT bridge: pure discovery/state/command mapping, and an end-to-end run
where a scripted loopback broker plays Home Assistant against a real Core — the
van announces its entities, streams state, and takes commands back through the
safety layer (a refused command snaps back)."""

from __future__ import annotations

import asyncio
import json
import struct

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.entities import Entity
from openvan_core.habridge import discovery, parse_command, render_state
from openvan_core.transports.mqtt import (
    build_publish,
    parse_publish,
    read_remaining_length,
)

_DEVICE = {"identifiers": ["openvan"], "name": "OpenVan"}


def _entity(**kw) -> Entity:
    base = dict(entity_id="sensor.x", name="X", domain="sensor", category="energy", state=1)
    base.update(kw)
    return Entity(**base)


# --- pure mapping ------------------------------------------------------------

def test_sensor_discovery():
    topic, payload = discovery(
        _entity(entity_id="sensor.house_battery_soc", name="House Battery", unit="%", state=82.0),
        prefix="homeassistant", base="openvan", device=_DEVICE,
    )
    assert topic == "homeassistant/sensor/openvan/sensor_house_battery_soc/config"
    assert payload["unique_id"] == "openvan_sensor_house_battery_soc"
    assert payload["state_topic"] == "openvan/sensor.house_battery_soc/state"
    assert payload["availability_topic"] == "openvan/availability"
    assert payload["unit_of_measurement"] == "%"
    assert payload["device"] == _DEVICE


def test_light_discovery_has_command_topic():
    topic, payload = discovery(
        _entity(entity_id="light.cabin", name="Cabin Light", domain="light", state="off"),
        prefix="homeassistant", base="openvan", device=_DEVICE,
    )
    assert topic == "homeassistant/light/openvan/light_cabin/config"
    assert payload["command_topic"] == "openvan/light.cabin/set"


def test_climate_discovery_uses_facet_topics():
    _topic, payload = discovery(
        _entity(entity_id="climate.diesel_heater", name="Heater", domain="climate",
                state="off", attributes={"setpoint": 20.0}),
        prefix="homeassistant", base="openvan", device=_DEVICE,
    )
    assert payload["modes"] == ["off", "heat"]
    assert payload["mode_command_topic"] == "openvan/climate.diesel_heater/mode/set"
    assert payload["temperature_command_topic"] == "openvan/climate.diesel_heater/temp/set"
    assert "state_topic" not in payload


def test_camera_domain_is_skipped():
    assert discovery(
        _entity(entity_id="camera.rear", domain="camera", state="online"),
        prefix="homeassistant", base="openvan", device=_DEVICE,
    ) is None


def test_render_state_per_domain():
    assert render_state(_entity(state=82.0)) == "82.0"
    assert render_state(_entity(domain="light", state="on")) == "ON"
    assert render_state(_entity(domain="switch", state="off")) == "OFF"
    assert render_state(_entity(domain="binary_sensor", state=True)) == "ON"
    assert render_state(_entity(domain="climate", state="heating")) == "heat"
    assert render_state(_entity(domain="climate", state="off")) == "off"


def test_parse_command_mapping():
    on = parse_command("openvan", "openvan/light.cabin/set", b"ON")
    assert on.entity_id == "light.cabin" and on.command == "turn_on"
    assert on.source == "automation"
    off = parse_command("openvan", "openvan/switch.water_pump/set", b"OFF")
    assert off.command == "turn_off"
    heat = parse_command("openvan", "openvan/climate.diesel_heater/mode/set", b"heat")
    assert heat.command == "turn_on"
    temp = parse_command("openvan", "openvan/climate.diesel_heater/temp/set", b"21.5")
    assert temp.command == "set_temperature" and temp.params == {"temperature": 21.5}
    assert parse_command("openvan", "openvan/light.cabin/state", b"ON") is None
    assert parse_command("other", "openvan/light.cabin/set", b"ON") is None
    assert parse_command("openvan", "openvan/climate.diesel_heater/temp/set", b"warm") is None


# --- end to end: a scripted broker plays Home Assistant ----------------------

class _FakeHa:
    """A single-connection scripted broker/HA: records the bridge's publishes and
    can inject commands back at it."""

    def __init__(self) -> None:
        self.published: list[tuple[str, bytes, bool]] = []
        self.connect_flags: int | None = None
        self.will: tuple[str, bytes] | None = None
        self._writer: asyncio.StreamWriter | None = None
        self.server = None
        self.port = 0

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    def topics(self) -> dict[str, bytes]:
        out: dict[str, bytes] = {}
        for topic, payload, _r in self.published:
            out[topic] = payload
        return out

    async def send(self, topic: str, payload: bytes) -> None:
        assert self._writer is not None
        self._writer.write(build_publish(topic, payload))
        await self._writer.drain()

    async def _handle(self, reader, writer) -> None:
        self._writer = writer
        try:
            # CONNECT (capture flags + will), then CONNACK.
            first = await reader.readexactly(1)
            assert first[0] & 0xF0 == 0x10
            body = await reader.readexactly(await read_remaining_length(reader))
            # variable header: "MQTT" string(6) + level(1) + flags(1) + keepalive(2)
            self.connect_flags = body[7]
            rest = body[10:]
            (cid_len,) = struct.unpack("!H", rest[:2])
            rest = rest[2 + cid_len :]
            if self.connect_flags & 0x04:  # will flag → will topic + payload follow
                (wt_len,) = struct.unpack("!H", rest[:2])
                wtopic = rest[2 : 2 + wt_len].decode()
                rest = rest[2 + wt_len :]
                (wp_len,) = struct.unpack("!H", rest[:2])
                self.will = (wtopic, rest[2 : 2 + wp_len])
            writer.write(bytes([0x20, 0x02, 0x00, 0x00]))
            await writer.drain()
            while True:
                fixed = await reader.readexactly(1)
                length = await read_remaining_length(reader)
                body = await reader.readexactly(length) if length else b""
                ptype = fixed[0] & 0xF0
                if ptype == 0x80:  # SUBSCRIBE → SUBACK
                    writer.write(bytes([0x90, 0x03]) + body[:2] + bytes([0x00]))
                    await writer.drain()
                elif ptype == 0x30:  # PUBLISH from the bridge
                    topic, payload = parse_publish(body, (fixed[0] & 0x06) >> 1)
                    self.published.append((topic, payload, bool(fixed[0] & 0x01)))
                elif ptype == 0xE0:  # DISCONNECT
                    return
        except (asyncio.IncompleteReadError, ConnectionError, AssertionError):
            pass


async def _wait_for(predicate, timeout=4.0):
    for _ in range(int(timeout / 0.05)):
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


@pytest.fixture
async def ha_core(tmp_path):
    ha = _FakeHa()
    await ha.start()
    core = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, simulate=False, data_dir=tmp_path)
    )
    await core.start()
    await core.set_integration_enabled("mqtt_homeassistant", True)
    await core.set_integration_config(
        "mqtt_homeassistant", {"mode": "mqtt", "host": "127.0.0.1", "port": str(ha.port)}
    )
    assert await _wait_for(lambda: "openvan/availability" in ha.topics())
    try:
        yield ha, core
    finally:
        await core.stop()
        ha.server.close()


async def test_bridge_announces_the_van(ha_core):
    ha, core = ha_core
    assert await _wait_for(
        lambda: "homeassistant/sensor/openvan/sensor_house_battery_soc/config" in ha.topics()
    )
    topics = ha.topics()
    # Availability + last will so HA can mark us unavailable when we drive off.
    assert topics["openvan/availability"] == b"online"
    assert ha.will == ("openvan/availability", b"offline")
    # Discovery configs are retained and carry the shared device.
    raw = topics["homeassistant/sensor/openvan/sensor_house_battery_soc/config"]
    cfg = json.loads(raw)
    assert cfg["device"]["identifiers"] == ["openvan"]
    retained = {t for t, _p, r in ha.published if r}
    assert "homeassistant/sensor/openvan/sensor_house_battery_soc/config" in retained
    # States flow: the seeded battery level is published.
    assert topics["openvan/sensor.house_battery_soc/state"] == b"82.0"
    # The controllable ones announce command topics.
    light = json.loads(topics["homeassistant/light/openvan/light_cabin/config"])
    assert light["command_topic"] == "openvan/light.cabin/set"
    assert "homeassistant/climate/openvan/climate_diesel_heater/config" in topics


async def test_entity_change_streams_to_ha(ha_core):
    ha, core = ha_core
    await core.twin.set_signal("house_battery.soc", 64.0)
    assert await _wait_for(
        lambda: ha.topics().get("openvan/sensor.house_battery_soc/state") == b"64.0"
    )


async def test_ha_command_goes_through_safety_and_acts(ha_core):
    ha, core = ha_core
    await ha.send("openvan/light.cabin/set", b"ON")
    assert await _wait_for(lambda: core.hub.entities["light.cabin"].state == "on")
    assert await _wait_for(lambda: ha.topics().get("openvan/light.cabin/state") == b"ON")


async def test_refused_ha_command_snaps_back(ha_core):
    ha, core = ha_core
    # Critical battery → load-shedding refuses turn_on for the non-essential light.
    await core.twin.set_signal("house_battery.soc", 5.0)
    before = len([1 for t, _p, _r in ha.published if t == "openvan/light.cabin/state"])
    await ha.send("openvan/light.cabin/set", b"ON")
    assert await _wait_for(
        lambda: len([1 for t, _p, _r in ha.published if t == "openvan/light.cabin/state"]) > before
    )
    # The light did NOT turn on, and the bridge re-published the truth ("OFF").
    assert core.hub.entities["light.cabin"].state == "off"
    assert ha.topics()["openvan/light.cabin/state"] == b"OFF"


async def test_climate_temperature_command(ha_core):
    ha, core = ha_core
    await ha.send("openvan/climate.diesel_heater/temp/set", b"21.5")
    assert await _wait_for(
        lambda: core.hub.entities["climate.diesel_heater"].attributes.get("setpoint") == 21.5
    )
    assert await _wait_for(
        lambda: ha.topics().get("openvan/climate.diesel_heater/temp/state") == b"21.5"
    )


# --- import direction: HA MQTT Statestream → twin signals --------------------

def test_parse_statestream_mapping():
    from openvan_core.habridge import parse_statestream

    p = "homeassistant_statestream"
    assert parse_statestream(p, f"{p}/sensor/living_room_temperature/state", b"21.5") == \
        ("ha.sensor.living_room_temperature", 21.5)
    assert parse_statestream(p, f"{p}/binary_sensor/front_door/state", b"on") == \
        ("ha.binary_sensor.front_door", True)
    assert parse_statestream(p, f"{p}/device_tracker/johan_phone/state", b"not_home") == \
        ("ha.device_tracker.johan_phone", False)
    assert parse_statestream(p, f"{p}/sensor/mode/state", b"eco") == ("ha.sensor.mode", "eco")
    # Never re-import our own exported mirror; never fake unavailable readings.
    assert parse_statestream(p, f"{p}/sensor/openvan_house_battery_soc/state", b"82") is None
    assert parse_statestream(p, f"{p}/sensor/x/state", b"unavailable") is None
    # Shape/domain filters.
    assert parse_statestream(p, f"{p}/climate/heater/state", b"heat") is None
    assert parse_statestream(p, "other/sensor/x/state", b"1") is None
    assert parse_statestream(p, f"{p}/sensor/x/attributes", b"{}") is None


async def test_statestream_import_end_to_end(ha_core):
    ha, core = ha_core
    await ha.send(
        "homeassistant_statestream/sensor/living_room_temperature/state", b"21.5"
    )
    assert await _wait_for(
        lambda: core.twin.get("ha.sensor.living_room_temperature") == 21.5
    )
    # Auto-surfaced as an entity via the declared "ha." prefix — no UI code.
    assert await _wait_for(
        lambda: core.hub.get_entity("sensor.ha_sensor_living_room_temperature") is not None
    )
    entity = core.hub.get_entity("sensor.ha_sensor_living_room_temperature")
    assert entity.state == 21.5 and entity.unit == "°C"
    # Our own mirror coming back via statestream must NOT be re-imported.
    await ha.send("homeassistant_statestream/sensor/openvan_solar_power/state", b"240")
    await ha.send("homeassistant_statestream/binary_sensor/front_door/state", b"on")
    assert await _wait_for(lambda: core.twin.get("ha.binary_sensor.front_door") is True)
    assert core.twin.get("ha.sensor.openvan_solar_power") is None
