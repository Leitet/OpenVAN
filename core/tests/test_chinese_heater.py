"""Chinese diesel heater ("blue wire") driver: frame codec pinned to the
Afterburner reverse engineering, echo handling on the half-duplex wire, and the
Rule-2 control path end-to-end — a safety-refused start never reaches the wire."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.intents import Intent
from openvan_core.transports.links import SimSerialLink
from openvan_core.transports.modbus_rtu import crc16

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "integrations"))
from chinese_heater import (  # noqa: E402
    CMD_NOP,
    CMD_START,
    CMD_STOP,
    FRAME_LEN,
    build_controller_frame,
    extract_heater_frame,
    parse_heater_frame,
)


def make_heater_frame(
    run_state: int = 0,
    error: int = 0,
    supply_v: float = 12.6,
    fan_rpm: int = 0,
    heat_exchanger: int = 18,
    pump_hz: float = 0.0,
) -> bytes:
    """A heater (RX) frame in the Afterburner layout — the fake device's reply."""
    b = bytearray(FRAME_LEN)
    b[0], b[1] = 0x76, 0x16
    b[2], b[3] = run_state, error
    b[4:6] = int(supply_v * 10).to_bytes(2, "big")
    b[6:8] = fan_rpm.to_bytes(2, "big")
    b[8:10] = (0).to_bytes(2, "big")  # fan voltage
    b[10:12] = heat_exchanger.to_bytes(2, "big")
    b[16] = int(pump_hz * 10)
    b[19] = 23  # fixed-mode pump frequency (Afterburner default)
    b[20] = 100
    crc = crc16(bytes(b[:22]))
    b[22], b[23] = crc >> 8, crc & 0xFF
    return bytes(b)


class FakeHeater:
    """A scripted heater on the half-duplex wire: echoes the controller frame
    (as the single wire does), then replies. Starts on 0xA0, stops on 0x05."""

    def __init__(self) -> None:
        self.run_state = 0
        self.starts = 0
        self.demands: list[int] = []

    def __call__(self, tx: bytes) -> bytes | None:
        if len(tx) != FRAME_LEN or tx[0] != 0x76:
            return None
        if ((tx[22] << 8) | tx[23]) != crc16(tx[:22]):
            return None
        self.demands.append(tx[4])
        if tx[2] == CMD_START:
            self.starts += 1
            self.run_state = 5
        elif tx[2] == CMD_STOP:
            self.run_state = 0
        reply = make_heater_frame(
            run_state=self.run_state,
            error=1 if self.run_state else 0,
            fan_rpm=3200 if self.run_state else 0,
            heat_exchanger=95 if self.run_state else 18,
            pump_hz=2.8 if self.run_state else 0.0,
        )
        return tx + reply  # echo first — the controller hears itself


# --- frame codec -------------------------------------------------------------

def test_controller_frame_matches_afterburner_init_defaults():
    frame = build_controller_frame(CMD_START, 18, 20)
    # Byte-for-byte the Afterburner CProtocol::Init(CtrlMode) defaults.
    assert frame[:22] == bytes.fromhex("7616a012140e2b05aa119478013208230500012c0dac")
    # Modbus CRC-16 over the first 22 bytes, stored MSB-first.
    assert ((frame[22] << 8) | frame[23]) == crc16(frame[:22])
    assert build_controller_frame()[2] == CMD_NOP
    assert build_controller_frame(CMD_STOP)[2] == CMD_STOP
    assert build_controller_frame(thermostat=False)[13] == 0xCD
    assert build_controller_frame(prime=True)[17] == 0x5A


def test_heater_frame_parse_and_rejects():
    frame = make_heater_frame(run_state=5, error=1, supply_v=12.6, fan_rpm=3200,
                              heat_exchanger=95, pump_hz=2.8)
    data = parse_heater_frame(frame)
    assert data["run_state"] == 5 and data["state"] == "Running" and data["on"] is True
    assert data["error"] == 1 and data["error_text"] == "No error (running)"
    assert data["supply_voltage"] == 12.6
    assert data["fan_rpm"] == 3200
    assert data["heat_exchanger_temp"] == 95
    assert data["pump_hz"] == 2.8
    assert data["fixed_pump_hz"] == 2.3
    # CRC flip → rejected; short frame → rejected.
    bad = bytearray(frame)
    bad[5] ^= 0xFF
    assert parse_heater_frame(bytes(bad)) is None
    assert parse_heater_frame(frame[:20]) is None
    # Error states map honestly.
    off = parse_heater_frame(make_heater_frame(run_state=0, error=0))
    assert off["on"] is False and off["error_text"] == "No error"
    flame_out = parse_heater_frame(make_heater_frame(run_state=8, error=9))
    assert flame_out["error_text"] == "Flame extinguished"


def test_extract_skips_echo_and_resyncs():
    tx = build_controller_frame(CMD_START, 18, 20)
    reply = make_heater_frame(run_state=2)
    # Garbage, our own echo, then the heater's reply — as the real wire looks.
    buffer = bytearray(b"\x00\x76\x99" + tx + reply)
    frame = extract_heater_frame(buffer, skip=tx)
    assert frame == reply
    assert extract_heater_frame(buffer, skip=tx) is None  # buffer drained
    # A partial frame stays buffered until the rest arrives.
    buffer = bytearray(reply[:10])
    assert extract_heater_frame(buffer) is None
    buffer += reply[10:]
    assert extract_heater_frame(buffer) == reply


# --- end-to-end through Core (Rule 2) ----------------------------------------

@pytest.fixture
async def core(tmp_path):
    c = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, simulate=False, data_dir=tmp_path)
    )
    await c.start()
    yield c
    await c.stop()


async def _live_heater(core, fake: FakeHeater):
    inst = core.integrations.get("chinese_heater")
    inst._make_link = lambda: SimSerialLink(responder=fake)
    await core.set_integration_enabled("chinese_heater", True)
    await core.set_integration_config(
        "chinese_heater", {"mode": "link", "host": "x", "poll_s": "0.02"}
    )
    for _ in range(60):
        if inst.live and core.twin.get("cdh.run_state") is not None:
            break
        await asyncio.sleep(0.02)
    return inst


async def _wait_run_state(core, value: int) -> None:
    for _ in range(60):
        if core.twin.get("cdh.run_state") == value:
            return
        await asyncio.sleep(0.02)
    assert core.twin.get("cdh.run_state") == value


async def test_intent_starts_and_stops_the_heater(core):
    fake = FakeHeater()
    inst = await _live_heater(core, fake)
    assert inst.live is True
    assert core.twin.get("cdh.run_state") == 0

    result = await core.hub.execute_intent(
        Intent("climate.diesel_heater", "set_temperature", {"temperature": 22})
    )
    assert result.ok
    result = await core.hub.execute_intent(Intent("climate.diesel_heater", "turn_on"))
    assert result.ok
    await _wait_run_state(core, 5)
    assert fake.starts == 1
    assert core.twin.get("cdh.supply_voltage") == 12.6
    assert core.twin.get("cdh.heat_exchanger_temp") == 95
    # The demand byte carried the safety-approved setpoint.
    assert 22 in fake.demands

    result = await core.hub.execute_intent(Intent("climate.diesel_heater", "turn_off"))
    assert result.ok
    await _wait_run_state(core, 0)
    assert fake.run_state == 0


async def test_safety_refused_start_never_reaches_the_wire(core):
    fake = FakeHeater()
    await _live_heater(core, fake)

    # No diesel → FuelRequiredToStart refuses the intent (Rule 2).
    await core.twin.set_signal("diesel_tank.level_pct", 0.0)
    result = await core.hub.execute_intent(Intent("climate.diesel_heater", "turn_on"))
    assert not result.ok

    await asyncio.sleep(0.2)  # several poll cycles
    assert fake.starts == 0
    assert fake.run_state == 0
    assert core.twin.get("cdh.run_state") == 0
