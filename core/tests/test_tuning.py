"""Feature tuning — thresholds/setpoints are config-driven and overridable."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import DEFAULT_TUNING, Config
from openvan_core.notices import CarbonMonoxide, default_advisors


def _cfg(tmp_path, **kw):
    return Config(
        ai_enabled=False, weather_enabled=False, memory_enabled=False,
        telemetry_enabled=False, data_dir=tmp_path, **kw,
    )


def test_tune_falls_back_to_default(tmp_path):
    cfg = _cfg(tmp_path, tuning={"co_warn_ppm": 5.0})
    assert cfg.tune("co_warn_ppm") == 5.0  # override
    assert cfg.tune("fridge_warm_c") == DEFAULT_TUNING["fridge_warm_c"]  # default


def test_default_advisors_use_config_thresholds(tmp_path):
    cfg = _cfg(tmp_path, tuning={"co_warn_ppm": 5.0})
    co = [a for a in default_advisors(cfg) if isinstance(a, CarbonMonoxide)][0]
    assert co.warn_ppm == 5.0
    # Bare (no config) still works with built-in defaults.
    assert [a for a in default_advisors() if isinstance(a, CarbonMonoxide)][0].warn_ppm == 35.0


async def test_override_changes_advisor_firing(tmp_path):
    core = build_core(_cfg(tmp_path, tuning={"co_warn_ppm": 5.0, "co_danger_ppm": 8.0}))
    await core.start()
    try:
        await core.twin.set_signal("air.co_ppm", 6.0)  # below default 35, above 5
        keys = {n["key"] for n in core.advisors.active_notices()}
        assert "carbon_monoxide" in keys  # fired only because of the override
    finally:
        await core.stop()


async def test_scene_setpoint_is_configurable(tmp_path):
    core = build_core(_cfg(tmp_path, tuning={"scene_sleep_c": 18.0}))
    await core.start()
    try:
        await core.twin.set_signal("house_battery.soc", 85)
        await core.twin.set_signal("diesel_tank.level_pct", 60)
        await core.run_scene("goodnight")
        assert core.hub.entities["climate.diesel_heater"].attributes["setpoint"] == 18.0
    finally:
        await core.stop()


async def test_maintenance_interval_override(tmp_path):
    core = build_core(_cfg(tmp_path, maintenance_intervals={"engine_service": 30000.0}))
    await core.start()
    try:
        status = {s["id"]: s for s in core.maintenance_status()}
        # 30000 interval over odo 48210 → window 30000, next 60000.
        assert status["engine_service"]["next_km"] == 60000
    finally:
        await core.stop()


async def test_apply_settings_updates_tuning_live(tmp_path):
    core = build_core(_cfg(tmp_path))
    await core.start()
    try:
        await core.apply_settings(tuning={"fridge_warm_c": 3.0})
        # settings() reflects it, and the rebuilt advisor fires at the new threshold.
        assert core.settings()["tuning"]["fridge_warm_c"] == 3.0
        await core.twin.set_signal("fridge.temp_c", 5.0)  # >3, would be fine at default 8
        keys = {n["key"] for n in core.advisors.active_notices()}
        assert "fridge_warm" in keys
    finally:
        await core.stop()


def test_partial_tuning_persists_by_merge(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.apply({"tuning": {"co_warn_ppm": 9.0}})  # partial
    assert cfg.tuning["co_warn_ppm"] == 9.0
    assert cfg.tuning["fridge_warm_c"] == DEFAULT_TUNING["fridge_warm_c"]  # untouched
