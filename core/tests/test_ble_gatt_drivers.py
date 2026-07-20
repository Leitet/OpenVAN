"""GATT substrate + the drivers on it: JBD BMS end-to-end against a scripted
SimBleDevice, Victron Instant Readout decrypt/parse round-trips, TPMS vectors."""

from __future__ import annotations

import asyncio
import struct

import pytest

from openvan_core import build_core
from openvan_core.aesctr import aes128_ctr
from openvan_core.ble import Advertisement, SimBleDevice
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


async def _wait_for(predicate, timeout=3.0):
    for _ in range(int(timeout / 0.05)):
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


# --- GATT substrate ----------------------------------------------------------

async def test_sim_gatt_device_roundtrip(core):
    writes = []

    async def on_write(dev, char, data):
        writes.append((char, data))
        await dev.notify("ff01", b"echo:" + data)

    device = SimBleDevice("AA:00:00:00:00:99", characteristics={"180f": b"\x55"}, on_write=on_write)
    core.ble.sim_device(device)
    session = await core.ble.connect("aa:00:00:00:00:99")
    assert await session.read("180f") == b"\x55"
    got = []
    await session.start_notify("ff01", lambda d: got.append(d))
    await session.write("ff02", b"ping")
    assert writes == [("ff02", b"ping")] and got == [b"echo:ping"]
    with pytest.raises(ConnectionError):
        await core.ble.connect("no:such:device")


# --- JBD BMS -----------------------------------------------------------------

def _jbd_response(payload: bytes) -> bytes:
    from ble_bms import checksum

    body = bytes([0x00, len(payload)]) + payload
    return b"\xdd\x03" + body + struct.pack(">H", checksum(body)) + b"\x77"


def _basic_info_payload() -> bytes:
    head = struct.pack(">HhHHH", 1320, -420, 8000, 10000, 42)  # V/I/remain/nominal/cycles
    prod_bal_prot = bytes(2) + bytes(4) + bytes(2)  # date, balance, protection
    tail = bytes([0x20, 81, 0x03, 4, 1]) + struct.pack(">H", 2981)  # ver, soc, fets, cells, 1 NTC @25.0C
    return head + prod_bal_prot + tail


def test_jbd_request_is_canonical(core):
    from ble_bms import build_request

    assert build_request(0x03) == bytes.fromhex("dda50300fffd77")


def test_jbd_parse_and_checksum_reject(core):
    from ble_bms import parse_basic_info, parse_frame

    frame = _jbd_response(_basic_info_payload())
    cmd, payload = parse_frame(frame)
    assert cmd == 0x03
    info = parse_basic_info(payload)
    assert info["voltage"] == 13.2 and info["current"] == -4.2
    assert info["soc"] == 81.0 and info["cycles"] == 42.0
    assert info["temperature"] == pytest.approx(25.0)
    assert info["charging_enabled"] == 1.0 and info["discharging_enabled"] == 1.0
    # Flip a payload byte → checksum mismatch → rejected.
    bad = bytearray(frame)
    bad[10] ^= 0xFF
    assert parse_frame(bytes(bad)) is None


def test_jbd_frame_buffer_reassembles_and_resyncs(core):
    from ble_bms import FrameBuffer

    frame = _jbd_response(_basic_info_payload())
    buf = FrameBuffer()
    assert buf.feed(b"\x99" + frame[:10]) == []  # junk prefix + partial
    assert buf.feed(frame[10:]) == [frame]


async def test_jbd_end_to_end_feeds_house_battery(core):
    frame = _jbd_response(_basic_info_payload())

    async def on_write(dev, char, data):
        if char == "ff02":
            await dev.notify("ff01", frame[:9])  # split across two notifications
            await dev.notify("ff01", frame[9:])

    core.ble.sim_device(SimBleDevice("A4:C1:38:00:BE:E5", on_write=on_write))
    await core.set_integration_enabled("ble_bms", True)
    await core.set_integration_config(
        "ble_bms", {"mode": "ble", "address": "A4:C1:38:00:BE:E5", "poll_s": "0.05"}
    )
    assert await _wait_for(lambda: core.twin.get("blebms.bee5.soc") == 81.0)
    assert core.twin.get("blebms.bee5.voltage") == 13.2
    # The layering payoff: a non-Victron pack drives the core battery signals.
    assert await _wait_for(lambda: core.twin.get("house_battery.soc") == 81.0)
    assert core.integrations.get("ble_bms").live is True


# --- Victron Instant Readout -------------------------------------------------

class BitWriter:
    def __init__(self) -> None:
        self.bits: list[int] = []

    def write(self, value: int, n: int) -> None:
        for i in range(n):
            self.bits.append((value >> i) & 1)

    def bytes(self) -> bytes:
        out = bytearray((len(self.bits) + 7) // 8)
        for pos, bit in enumerate(self.bits):
            out[pos >> 3] |= bit << (pos & 7)
        return bytes(out)


def _victron_frame(record_type: int, plain: bytes, key: bytes, iv: int = 0x1234) -> bytes:
    header = b"\x10\x02" + b"\x00\xa0" + bytes([record_type]) + iv.to_bytes(2, "little") + key[:1]
    return header + aes128_ctr(key, iv, plain)


def test_victron_battery_monitor_roundtrip(core):
    from victron_ble import RECORD_BATTERY_MONITOR, decrypt, parse_battery_monitor

    w = BitWriter()
    w.write(600, 16)          # TTG 600 min
    w.write(1320, 16)         # 13.20 V
    w.write(0, 16)            # no alarm
    w.write(0, 16)            # aux
    w.write(3, 2)             # aux mode: disabled
    w.write((1 << 22) - 5000, 22)  # -5.000 A
    w.write(120, 20)          # 12.0 Ah consumed
    w.write(815, 10)          # 81.5 %
    plain = w.bytes()

    key = bytes(range(16))
    frame = _victron_frame(RECORD_BATTERY_MONITOR, plain, key)
    record_type, decrypted = decrypt(frame, key)
    assert record_type == RECORD_BATTERY_MONITOR
    data = parse_battery_monitor(decrypted)
    assert data["ttg_min"] == 600.0
    assert data["voltage"] == 13.2
    assert data["current"] == -5.0
    assert data["consumed_ah"] == 12.0
    assert data["soc"] == 81.5
    # Wrong key (different first byte) → key-check mismatch → None.
    assert decrypt(frame, b"\xff" * 16) is None


def test_victron_solar_roundtrip_with_sentinels(core):
    from victron_ble import RECORD_SOLAR, decrypt, parse_solar

    w = BitWriter()
    w.write(4, 8)        # absorption
    w.write(0, 8)        # no error
    w.write(1350, 16)    # 13.50 V
    w.write(52, 16)      # 5.2 A
    w.write(123, 16)     # 1230 Wh today
    w.write(180, 16)     # 180 W PV
    w.write(0x1FF, 9)    # load: unavailable sentinel
    key = b"\xab" * 16
    record_type, plain = decrypt(_victron_frame(RECORD_SOLAR, w.bytes(), key), key)
    data = parse_solar(plain)
    assert data["charge_state"] == 4.0
    assert data["battery_voltage"] == 13.5
    assert data["yield_today_wh"] == 1230.0
    assert data["pv_power"] == 180.0
    assert "load_current" not in data  # sentinel respected


def test_victron_key_parsing(core):
    from victron_ble import parse_keys

    keys = parse_keys("AA:BB:CC:DD:EE:FF = 000102030405060708090a0b0c0d0e0f, bad, x=zz")
    assert list(keys) == ["aa:bb:cc:dd:ee:ff"]
    assert keys["aa:bb:cc:dd:ee:ff"][0] == 0x00


async def test_victron_advertisement_through_core(core):
    from victron_ble import RECORD_BATTERY_MONITOR

    w = BitWriter()
    w.write(0xFFFF, 16)  # TTG unavailable
    w.write(1290, 16)
    w.write(0, 16)
    w.write(0, 16)
    w.write(3, 2)
    w.write((1 << 22) - 4200, 22)
    w.write(0xFFFFF, 20)
    w.write(820, 10)
    key = bytes(range(16))
    frame = _victron_frame(RECORD_BATTERY_MONITOR, w.bytes(), key)

    await core.set_integration_enabled("victron_ble", True)
    await core.set_integration_config(
        "victron_ble",
        {"keys": "C0:01:00:00:CA:FE=" + key.hex(), "feeds_house_battery": "yes"},
    )
    await core.ble.inject(Advertisement(address="C0:01:00:00:CA:FE",
                                        manufacturer_data={0x02E1: frame}))
    assert core.twin.get("victronble.cafe.soc") == 82.0
    assert core.twin.get("house_battery.soc") == 82.0  # opted-in mirror


# --- TPMS --------------------------------------------------------------------

def test_tpms_vector(core):
    from tpms import parse_tpms

    payload = bytes(6) + struct.pack("<iib?", 260000, 2350, 85, False)
    data = parse_tpms(payload)
    assert data == {"pressure_bar": 2.6, "temperature": 23.5, "battery_pct": 85.0, "alarm": 0.0}
    assert parse_tpms(b"\x00" * 10) is None  # wrong length


async def test_tpms_advertisement_becomes_entity(core):
    await core.set_integration_enabled("tpms", True)
    await core.ble.inject(Advertisement(
        address="80:EA:CA:00:00:F1",
        manufacturer_data={0x0100: bytes(6) + struct.pack("<iib?", 210000, 1800, 60, True)},
    ))
    assert core.twin.get("tpms.00f1.pressure_bar") == 2.1
    assert core.twin.get("tpms.00f1.alarm") == 1.0
    assert "sensor.tpms_00f1_pressure_bar" in core.hub.entities
