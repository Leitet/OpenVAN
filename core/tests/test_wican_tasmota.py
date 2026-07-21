"""WiCAN (OBD-II over MQTT) + Tasmota drivers, and the signal-freshness contract:
when a live transport drops, its readings are honestly marked stale."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.intents import Intent

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "integrations"))
from wican import parse_autopid, snake  # noqa: E402
from tasmota import flatten_sensor, parse_power  # noqa: E402

from test_transports import _mqtt_broker  # noqa: E402  (loopback broker helper)


@pytest.fixture
async def core(tmp_path):
    c = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, data_dir=tmp_path)
    )
    await c.start()
    yield c
    await c.stop()


# --- WiCAN parsers -----------------------------------------------------------

def test_snake_case():
    assert snake("VehicleSpeed") == "vehicle_speed"
    assert snake("EngineRPM") == "engine_rpm"
    assert snake("fuel-level") == "fuel_level"


def test_parse_autopid():
    payload = b'{"VehicleSpeed": 62, "EngineRPM": 1850.5, "Lock": "on", "Note": "hi"}'
    assert parse_autopid(payload) == {
        "vehicle_speed": 62.0, "engine_rpm": 1850.5, "lock": True,
    }
    assert parse_autopid(b"not json") == {}
    assert parse_autopid(b"[1,2]") == {}


# --- WiCAN end-to-end + freshness on drop ------------------------------------

async def test_wican_live_then_stale_on_drop(core):
    server, port = await _mqtt_broker(
        "wican/wican/can/rx", b'{"VehicleSpeed": 62, "FuelLevel": 43}'
    )
    async with server:
        await core.set_integration_enabled("wican", True)
        await core.set_integration_config(
            "wican", {"mode": "mqtt", "host": "127.0.0.1", "port": str(port)}
        )
        for _ in range(60):
            if core.twin.get("obd.vehicle_speed") == 62.0:
                break
            await asyncio.sleep(0.05)
        assert core.twin.get("obd.vehicle_speed") == 62.0
        assert core.twin.get("obd.fuel_level") == 43.0
        # Live OBD speed drives the world's speed signal.
        assert core.twin.get("vehicle.speed_kmh") == 62.0
        assert core.integrations.get("wican").live is True

    # The broker held ~0.3 s then dropped: the supervisor must mark the driver's
    # readings stale — last-known values, never shown as current.
    for _ in range(60):
        if "obd.vehicle_speed" in core.twin.stale():
            break
        await asyncio.sleep(0.05)
    assert "obd.vehicle_speed" in core.twin.stale()
    # A fresh write (reconnect, sim, bench) clears the flag.
    await core.twin.set_signal("obd.vehicle_speed", 0.0, source="sim")
    assert "obd.vehicle_speed" not in core.twin.stale()


# --- Tasmota parsers ---------------------------------------------------------

def test_flatten_sensor():
    payload = (b'{"Time":"2026-07-21T10:00:00",'
               b'"ENERGY":{"Power":12.4,"Total":1.234},'
               b'"AM2301":{"Temperature":21.5,"Humidity":48}}')
    assert flatten_sensor(payload) == {
        "energy_power": 12.4, "energy_total": 1.234,
        "am2301_temperature": 21.5, "am2301_humidity": 48.0,
    }
    assert flatten_sensor(b"junk") == {}


def test_parse_power():
    assert parse_power(b"ON") is True
    assert parse_power(b"off") is False
    assert parse_power(b"toggle") is None


# --- Tasmota sim mode: safety-checked switch + auto sensors ------------------

async def test_tasmota_switch_through_safety_and_auto_sensors(core):
    await core.set_integration_enabled("tasmota", True)
    entity = core.hub.get_entity("switch.tasmota_tasmota_plug")
    assert entity is not None and entity.controllable

    result = await core.hub.execute_intent(Intent("switch.tasmota_tasmota_plug", "turn_on"))
    assert result.ok
    assert core.twin.get("tasmota.tasmota_plug.on") is True
    await core.integrations.simulate_all(1.0)
    assert core.twin.get("tasmota.tasmota_plug.energy_power") == 8.5
    # Auto-surfaced sensor entity via the declared "tasmota." prefix.
    await core.integrations.simulate_all(1.0)
    power = core.hub.entities.get("sensor.tasmota_tasmota_plug_energy_power")
    assert power is not None and power.state == 8.5


async def test_tasmota_live_command_publishes_to_broker(core):
    class FakeClient:
        def __init__(self) -> None:
            self.published: list[tuple[str, bytes]] = []

        async def publish(self, topic: str, payload: bytes, retain: bool = False) -> None:
            self.published.append((topic, payload))

    await core.set_integration_enabled("tasmota", True)
    inst = core.integrations.get("tasmota")
    fake = FakeClient()
    inst._client = fake
    inst.live = True
    # Command path (post-safety): live → the broker gets the cmnd, twin untouched
    # (the device's own stat echo is what flips the state).
    result = await core.hub.execute_intent(Intent("switch.tasmota_tasmota_plug", "turn_on"))
    assert result.ok
    assert fake.published == [("cmnd/tasmota_plug/POWER", b"ON")]
    assert core.twin.get("tasmota.tasmota_plug.on") is not True


async def test_tasmota_devices_config_dedupes(core):
    inst = core.integrations.get("tasmota")
    inst.config["devices"] = [
        {"topic": "Fridge Plug", "name": "Fridge"},
        {"topic": "fridge_plug", "name": "dup"},
        {"topic": "", "name": "nope"},
    ]
    assert inst.devices() == [{"topic": "fridge_plug", "name": "Fridge"}]
