"""Travel memory — stay detection, notes, energy, recall."""

from __future__ import annotations

from openvan_core.config import Config
from openvan_core.memory import TravelMemory


class FakeTwin:
    def __init__(self, **signals):
        self._s = dict(signals)

    def get(self, key, default=None):
        return self._s.get(key, default)

    def set(self, key, value):
        self._s[key] = value


def _memory(tmp_path, twin, telemetry=None):
    cfg = Config(data_dir=tmp_path, memory_dwell_s=60.0)
    mem = TravelMemory(cfg, twin, telemetry=telemetry)
    mem.open()
    return mem


def test_stay_opens_after_dwell_and_closes_on_drive(tmp_path):
    twin = FakeTwin(**{
        "vehicle.ignition": False, "vehicle.speed_kmh": 0.0,
        "gps.lat": 46.0, "gps.lon": 11.0, "house_battery.soc": 90.0,
    })
    mem = _memory(tmp_path, twin)

    mem.tick(1000.0)  # stationary begins, dwell not yet reached
    assert mem.current() is None
    mem.tick(1000.0 + 61)  # past dwell -> stay opens
    cur = mem.current()
    assert cur is not None and cur["open"] and cur["lat"] == 46.0
    assert cur["arrival_soc"] == 90.0

    # drive away -> stay closes with departure soc
    twin.set("vehicle.ignition", True)
    twin.set("vehicle.speed_kmh", 40.0)
    twin.set("house_battery.soc", 82.0)
    mem.tick(1000.0 + 3661)
    assert mem.current() is None
    stays = mem.list_stays()
    assert len(stays) == 1 and not stays[0]["open"]
    assert stays[0]["soc_used_pct"] == 8.0  # 90 -> 82
    mem.close()


def test_traffic_stop_does_not_log(tmp_path):
    twin = FakeTwin(**{"vehicle.ignition": True, "vehicle.speed_kmh": 0.0})
    mem = _memory(tmp_path, twin)
    mem.tick(1000.0)
    mem.tick(1030.0)  # 30s < 60s dwell
    twin.set("vehicle.speed_kmh", 50.0)
    mem.tick(1035.0)
    assert mem.list_stays() == []
    mem.close()


def test_bookmark_note_and_place(tmp_path):
    twin = FakeTwin(**{"gps.lat": 46.5, "gps.lon": 11.6, "house_battery.soc": 77.0})
    mem = _memory(tmp_path, twin)
    booked = mem.bookmark("beautiful lake, quiet")
    assert booked is not None and booked["notes"] == "beautiful lake, quiet"
    mem.set_place("Lago di Braies")
    mem.add_note("came back at sunset")
    latest = mem.list_stays()[0]
    assert latest["place"] == "Lago di Braies"
    assert "sunset" in latest["notes"]
    mem.close()


def test_solar_energy_over_stay(tmp_path):
    from openvan_core.telemetry import TelemetryStore

    tel = TelemetryStore(tmp_path / "t.db")
    tel.open()
    tel.record("solar.power", 200.0, 1000.0)
    tel.record("solar.power", 200.0, 4600.0)  # 200W for 1h -> 200 Wh

    twin = FakeTwin(**{
        "vehicle.ignition": False, "vehicle.speed_kmh": 0.0,
        "gps.lat": 46.0, "gps.lon": 11.0, "house_battery.soc": 90.0,
    })
    mem = _memory(tmp_path, twin, telemetry=tel)
    mem.tick(1000.0)
    mem.tick(1061.0)  # open
    twin.set("vehicle.ignition", True)
    twin.set("vehicle.speed_kmh", 30.0)
    mem.tick(4600.0)  # close after the solar window
    assert mem.list_stays()[0]["solar_wh"] is not None
    mem.close()
    tel.close()
