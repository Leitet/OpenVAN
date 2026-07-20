"""BLE drivers on the shared substrate: parser vectors (BTHome v2, Ruuvi RAWv2,
Mopeka Pro Check) and the end-to-end story — an injected advertisement flows
scanner → driver → twin → auto-entity, and a low Mopeka tank frame lights up the
existing LowPropane advisor with zero advisor changes (the layering payoff)."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.ble import Advertisement
from openvan_core.config import Config


@pytest.fixture
async def core(tmp_path):
    c = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, simulate=False, ble_radio="sim",
               data_dir=tmp_path)
    )
    await c.start()
    yield c
    await c.stop()


# --- parser vectors ----------------------------------------------------------

def test_bthome_v2_vector(core):
    from bthome import parse_bthome

    payload = bytes.fromhex("4001550 2ca09 03bf13".replace(" ", ""))
    data = parse_bthome(payload)
    assert data == {"battery_pct": 85.0, "temperature": 25.06, "humidity": 50.55}


def test_bthome_rejects_encrypted_and_v1(core):
    from bthome import parse_bthome

    assert parse_bthome(bytes.fromhex("410155")) is None  # encrypted bit set
    assert parse_bthome(bytes.fromhex("20015 5".replace(" ", ""))) is None  # version 1
    # Unknown object id stops the parse but keeps what came before it.
    assert parse_bthome(bytes.fromhex("400155ff1234")) == {"battery_pct": 85.0}


def test_ruuvi_rawv2_vector(core):
    from ruuvitag import parse_rawv2

    payload = bytes.fromhex("05" "0954" "5194" "c87e" "000000000000" "ac20")
    data = parse_rawv2(payload)
    assert data == {
        "temperature": 11.94,
        "humidity": 52.21,
        "pressure_hpa": 1013.26,
        "battery": 2.977,
    }
    assert parse_rawv2(bytes.fromhex("03aabb")) is None  # not format 5


def test_mopeka_vector(core):
    from mopeka import level_pct, parse_mopeka

    data = parse_mopeka(bytes([0x03, 0x59, 0x3E, 0x90, 0x01]))
    assert data["battery_v"] == pytest.approx(2.781)
    assert data["temperature"] == 22.0
    assert data["level_mm"] == pytest.approx(203.3, abs=0.1)
    assert data["quality"] == 0.0
    assert level_pct(data["level_mm"], 254.0) == pytest.approx(80.1, abs=0.1)
    assert parse_mopeka(b"\x03\x59") is None  # short frame


# --- end to end through the substrate ----------------------------------------

async def test_bthome_advertisement_becomes_an_entity(core):
    await core.set_integration_enabled("bthome", True)
    await core.ble.inject(Advertisement(
        address="AA:BB:CC:DD:EE:F1",
        name="Fridge Probe",
        service_data={"fcd2": bytes.fromhex("400155" "02ca09" "03bf13")},
    ))
    assert core.twin.get("bthome.fridge_probe.temperature") == 25.06
    assert core.twin.get("bthome.fridge_probe.humidity") == 50.55
    # device_sensors auto-surfaces it — €10 sensor to dashboard, no code.
    entity = core.hub.entities.get("sensor.bthome_fridge_probe_temperature")
    assert entity is not None and entity.unit == "°C"


async def test_ruuvi_advertisement_flows(core):
    await core.set_integration_enabled("ruuvitag", True)
    await core.ble.inject(Advertisement(
        address="C4:64:00:00:BE:EF",
        manufacturer_data={0x0499: bytes.fromhex("05" "0954" "5194" "c87e" "000000000000" "ac20")},
    ))
    assert core.twin.get("ruuvitag.beef.temperature") == 11.94


async def test_mopeka_low_tank_fires_the_existing_propane_advisor(core):
    await core.set_integration_enabled("mopeka", True)
    # A low frame: raw=0x50 → ~41 mm → ~16% of a 254 mm cylinder.
    await core.ble.inject(Advertisement(
        address="DD:00:00:00:00:01",
        manufacturer_data={0x0059: bytes([0x03, 0x59, 0x3E, 0x50, 0x00])},
    ))
    assert core.twin.get("mopeka.0001.level_pct") == pytest.approx(16.0, abs=0.5)
    # Mirrored into the core tank signal → the untouched LowPropane advisor fires.
    assert core.twin.get("propane.level_pct") == pytest.approx(16.0, abs=0.5)
    keys = {n["key"] for n in core.advisors.active_notices()}
    assert "propane_low" in keys


async def test_unsubscribed_when_disabled(core):
    await core.set_integration_enabled("bthome", True)
    await core.set_integration_enabled("bthome", False)
    await core.ble.inject(Advertisement(
        address="AA:BB:CC:DD:EE:F2",
        service_data={"fcd2": bytes.fromhex("400155")},
    ))
    assert core.twin.get("bthome.eef2.battery_pct") is None  # no longer listening


def test_ble_http_surface(tmp_path):
    from fastapi.testclient import TestClient
    from openvan_core.api import build_app

    cfg = Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
                 telemetry_enabled=False, simulate=True, ble_radio="sim", data_dir=tmp_path)
    with TestClient(build_app(cfg)) as client:
        status = client.get("/api/ble").json()
        assert status["radio"] == "sim" and status["available"] is True

        client.post("/api/integrations", json={"id": "bthome", "enabled": True})
        out = client.post("/api/sim/ble", json={
            "address": "AA:BB:CC:DD:EE:F3",
            "name": "bench probe",
            "service_data": {"fcd2": "400155" + "02ca09"},
        })
        assert out.status_code == 200
        twin = client.get("/api/state").json()["twin"]
        assert twin.get("bthome.bench_probe.temperature") == 25.06

        bad = client.post("/api/sim/ble", json={"address": "x", "service_data": {"fcd2": "zz"}})
        assert bad.status_code == 400
