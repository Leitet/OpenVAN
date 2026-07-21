"""Votronic Display Link driver: codec pinned to real example frames captured
from a Smart Shunt 400 S (via syssi/esphome-votronic, Apache-2.0), resync on
the passive bus, and end-to-end through Core with house-battery mirroring."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.transports.links import SimSerialLink

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "integrations"))
from votronic import checksum, extract_frames, parse_frame  # noqa: E402

# Real captures (Smart Shunt 400 S) — from the reference component's comments.
INFO1 = bytes.fromhex("AACA03050F05C70120006300 7BFEFF39".replace(" ", ""))
INFO2 = bytes.fromhex("AADA00000000F8115E0700002F040243")
INFO3 = bytes.fromhex("AAFA2F000000D202000A000028D000F7")


def test_checksum_matches_real_captures():
    for frame in (INFO1, INFO2, INFO3):
        assert checksum(frame) == frame[-1]


def test_parse_battery_computer_frames():
    group, m = parse_frame(INFO1)
    assert group == "battery"
    assert m["voltage"] == 12.83       # 0x0503 * 10 mV
    assert m["battery2_voltage"] == 12.95
    assert m["capacity_remaining_ah"] == 455.0
    assert m["soc"] == 99.0
    assert m["current"] == -0.389      # 0xFE7B signed * 1 mA
    group, m = parse_frame(INFO2)
    assert group == "battery"
    assert m["nominal_capacity_ah"] == 460.0
    assert parse_frame(INFO3) is None  # undocumented type → skipped honestly


def test_parse_solar_frame():
    # Synthetic solar frame: batt 12.9 V, PV 17.0 V / 3.5 A, temp 25, active.
    body = bytearray(16)
    body[0], body[1] = 0xAA, 0x1A
    body[2:4] = (1290).to_bytes(2, "little")
    body[4:6] = (1700).to_bytes(2, "little")
    body[6:8] = (35).to_bytes(2, "little")
    body[11] = 25
    body[14] = 1 << 3
    body[15] = checksum(bytes(body))
    group, m = parse_frame(bytes(body))
    assert group == "solar"
    assert m["battery_voltage"] == 12.9
    assert m["pv_voltage"] == 17.0 and m["pv_current"] == 3.5
    assert m["pv_power"] == 59.5
    assert m["active"] is True


def test_extract_resyncs_past_garbage():
    # Garbage before each frame — including a false 0xAA sync — must be skipped.
    buffer = bytearray(b"\x00\xaa\x13" + INFO1 + b"\xaa\x01" + INFO2)
    assert extract_frames(buffer) == [INFO1, INFO2]
    # A partial frame stays buffered until the rest arrives.
    buffer = bytearray(INFO1[:9])
    assert extract_frames(buffer) == []
    buffer += INFO1[9:]
    assert extract_frames(buffer) == [INFO1]


@pytest.fixture
async def core(tmp_path):
    c = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, data_dir=tmp_path)
    )
    await c.start()
    yield c
    await c.stop()


async def test_votronic_live_over_sim_link(core):
    link = SimSerialLink()
    inst = core.integrations.get("votronic")
    inst._make_link = lambda: link
    await core.set_integration_enabled("votronic", True)
    await core.set_integration_config("votronic", {"mode": "link", "host": "x"})
    for _ in range(40):
        if inst.live:
            break
        await asyncio.sleep(0.05)
    link.feed(INFO1)
    link.feed(INFO2)
    for _ in range(40):
        if core.twin.get("votronic.battery.nominal_capacity_ah") == 460.0:
            break
        await asyncio.sleep(0.05)
    assert core.twin.get("votronic.battery.soc") == 99.0
    assert core.twin.get("votronic.battery.current") == -0.389
    # Mirrors: the shunt owns the house battery while live.
    assert core.twin.get("house_battery.soc") == 99.0
    assert core.twin.get("house_battery.voltage") == 12.83
