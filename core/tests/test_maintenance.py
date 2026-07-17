"""Maintenance schedule: odometer/date due logic, completion, persistence, advisor."""

from __future__ import annotations

from datetime import date

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.maintenance import MaintenanceLog
from openvan_core.notices import ServiceDue
from openvan_core.store import ConfigStore


def _store(tmp_path):
    s = ConfigStore(tmp_path / "store.db")
    s.open()
    return s


def _log(tmp_path, odo=48210.0):
    log = MaintenanceLog(_store(tmp_path), get_odometer=lambda: odo)
    log.load()
    return log


def test_odometer_item_baselines_to_current_window(tmp_path):
    log = _log(tmp_path, odo=48210.0)
    status = {s["id"]: s for s in log.status(48210.0, date(2026, 7, 17))}
    eng = status["engine_service"]  # interval 15000
    # Baseline window 45000 → next 60000 → ~11790 km to go, not overdue.
    assert eng["next_km"] == 60000
    assert eng["remaining_km"] == pytest.approx(11790, abs=1)
    assert eng["due"] is False


def test_completing_resets_next_due(tmp_path):
    log = _log(tmp_path, odo=48210.0)
    log.complete("engine_service", 48210.0, date(2026, 7, 17))
    status = {s["id"]: s for s in log.status(50000.0, date(2026, 7, 17))}
    assert status["engine_service"]["next_km"] == 48210 + 15000


def test_date_item_due_logic(tmp_path):
    log = _log(tmp_path)
    log.complete("alarm_test", None, date(2026, 1, 1))  # done Jan 1
    # 180-day interval → next 2026-06-30; on 2026-07-17 it's overdue.
    s = {x["id"]: x for x in log.status(48210.0, date(2026, 7, 17))}["alarm_test"]
    assert s["due"] is True
    assert s["remaining_days"] < 0


def test_persistence_across_reload(tmp_path):
    store = _store(tmp_path)
    log = MaintenanceLog(store, get_odometer=lambda: 48210.0)
    log.load()
    log.complete("tyre_rotation", 48000.0, date(2026, 7, 17))
    log2 = MaintenanceLog(store, get_odometer=lambda: 48210.0)
    log2.load()
    assert log2.items["tyre_rotation"].last_km == 48000.0


@pytest.fixture
async def core(tmp_path):
    c = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False, data_dir=tmp_path)
    )
    await c.start()
    yield c
    await c.stop()


async def test_service_due_advisor_fires_when_overdue(core):
    # Force engine service overdue by recording it a full interval ago.
    core.complete_maintenance("engine_service")  # last_km = current odo
    core.maintenance.items["engine_service"].last_km = 0.0  # now way overdue
    n = ServiceDue(core.maintenance).evaluate(core.hub)
    assert n is not None
    assert "engine_service" in n.data["items"]
