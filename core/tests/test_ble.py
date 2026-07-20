"""BLE substrate: one shared scanner, filtered fanout, sim radio injection,
radio resolution — the base every BLE driver builds on."""

from __future__ import annotations

import pytest

from openvan_core.ble import Advertisement, BleScanner, SimBleRadio, short_uuid
from openvan_core.config import Config


def test_short_uuid_normalisation():
    assert short_uuid("0000FCD2-0000-1000-8000-00805F9B34FB") == "fcd2"
    assert short_uuid("fcd2") == "fcd2"
    # Non-Bluetooth-base UUIDs stay full (lowercased).
    assert short_uuid("12345678-1234-1234-1234-123456789ABC") == "12345678-1234-1234-1234-123456789abc"


async def test_sim_radio_injects_to_handler():
    radio = SimBleRadio()
    seen = []
    await radio.start(lambda adv: seen.append(adv))
    await radio.inject(Advertisement(address="AA:BB", rssi=-50))
    assert len(seen) == 1 and seen[0].address == "AA:BB"
    await radio.stop()
    await radio.inject(Advertisement(address="CC:DD"))
    assert len(seen) == 1  # stopped radios deliver nothing


def _scanner(**cfg) -> BleScanner:
    return BleScanner(Config(simulate=True, **cfg))


def test_radio_plan_resolution(monkeypatch):
    import openvan_core.ble as b

    monkeypatch.setattr(b, "_bleak_available", lambda: False)
    assert _scanner().plan == "sim"  # auto + simulate + no bleak
    assert _scanner(ble_radio="off").plan is None
    assert BleScanner(Config(simulate=False)).plan is None  # real van, no extra
    monkeypatch.setattr(b, "_bleak_available", lambda: True)
    assert _scanner().plan == "bleak"  # auto prefers a real adapter
    assert _scanner(ble_radio="sim").plan == "sim"  # pinned


async def test_filtered_fanout_and_unsubscribe(monkeypatch):
    import openvan_core.ble as b

    monkeypatch.setattr(b, "_bleak_available", lambda: False)
    scanner = _scanner()
    await scanner.start()
    ruuvi, bthome, anyadv = [], [], []
    scanner.subscribe(lambda a: ruuvi.append(a), manufacturer_id=0x0499)
    unsub = scanner.subscribe(lambda a: bthome.append(a), service_uuid="0000FCD2-0000-1000-8000-00805F9B34FB")
    scanner.subscribe(lambda a: anyadv.append(a))

    await scanner.inject(Advertisement(address="R1", manufacturer_data={0x0499: b"\x05"}))
    await scanner.inject(Advertisement(address="B1", service_data={"fcd2": b"\x40"}))
    assert [a.address for a in ruuvi] == ["R1"]
    assert [a.address for a in bthome] == ["B1"]
    assert [a.address for a in anyadv] == ["R1", "B1"]

    unsub()
    await scanner.inject(Advertisement(address="B2", service_data={"fcd2": b"\x40"}))
    assert [a.address for a in bthome] == ["B1"]  # unsubscribed
    await scanner.stop()


async def test_bad_subscriber_is_contained(monkeypatch):
    import openvan_core.ble as b

    monkeypatch.setattr(b, "_bleak_available", lambda: False)
    scanner = _scanner()
    await scanner.start()
    good = []

    def boom(_adv):
        raise RuntimeError("bad parser")

    scanner.subscribe(boom)
    scanner.subscribe(lambda a: good.append(a))
    await scanner.inject(Advertisement(address="X1"))
    assert len(good) == 1  # the bad parser never stalls the stream


async def test_address_prefix_filter(monkeypatch):
    import openvan_core.ble as b

    monkeypatch.setattr(b, "_bleak_available", lambda: False)
    scanner = _scanner()
    await scanner.start()
    seen = []
    scanner.subscribe(lambda a: seen.append(a), address_prefix="c4:64")
    await scanner.inject(Advertisement(address="C4:64:11:22:33:44"))
    await scanner.inject(Advertisement(address="AA:BB:11:22:33:44"))
    assert [a.address for a in seen] == ["C4:64:11:22:33:44"]


def test_status_reports_plan():
    s = _scanner(ble_radio="sim")
    assert s.status() == {"available": True, "radio": "sim", "running": False, "subscribers": 0}
