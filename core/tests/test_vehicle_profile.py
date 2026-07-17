"""Vehicle profile: presets, summary, leveling geometry, AI context."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.notices import NotLevel
from openvan_core.vehicle import PRESETS, presets_list, vehicle_summary


def _cfg(tmp_path, **kw):
    return Config(
        ai_enabled=False, weather_enabled=False, memory_enabled=False,
        telemetry_enabled=False, data_dir=tmp_path, **kw,
    )


def test_preset_library_is_broad():
    presets = presets_list()
    assert len(presets) >= 10
    ids = {p["id"] for p in presets}
    assert "citroen_jumper_l4h3" in ids
    jumper = PRESETS["citroen_jumper_l4h3"]
    assert jumper["height_mm"] == 2764 and jumper["wheelbase_mm"] == 4035
    assert jumper["category"] == "converted_van"
    for p in presets:
        s = p["spec"]
        for key in ("height_mm", "length_mm", "wheelbase_mm", "gross_weight_kg", "category"):
            assert key in s, f"{p['id']} missing {key}"


def test_vehicle_summary_converts_units():
    s = vehicle_summary(PRESETS["citroen_jumper_l4h3"])
    assert s["height_m"] == pytest.approx(2.76, abs=0.01)
    assert s["length_m"] == pytest.approx(6.36, abs=0.01)
    assert s["gross_weight_kg"] == 3500
    assert "Citroën Jumper" in s["name"]


def test_vehicle_summary_none_when_unset():
    assert vehicle_summary({}) is None
    assert vehicle_summary(None) is None


async def test_default_vehicle_drives_leveling_geometry(tmp_path):
    core = build_core(_cfg(tmp_path))
    await core.start()
    try:
        nl = next(a for a in core.advisors.advisors if isinstance(a, NotLevel))
        # Default preset (Jumper L3H2) → track 1810 mm, wheelbase 4035 mm.
        assert nl.track_m == pytest.approx(1.81)
        assert nl.wheelbase_m == pytest.approx(4.035)
    finally:
        await core.stop()


async def test_set_vehicle_rebuilds_leveling_and_persists(tmp_path):
    core = build_core(_cfg(tmp_path))
    await core.start()
    try:
        await core.set_vehicle({"make": "Test", "track_mm": 2200, "wheelbase_mm": 3200})
        nl = next(a for a in core.advisors.advisors if isinstance(a, NotLevel))
        assert nl.track_m == pytest.approx(2.2)
        assert nl.wheelbase_m == pytest.approx(3.2)
        state = core.vehicle_state()
        assert state["profile"]["make"] == "Test"
        assert len(state["categories"]) >= 5
        assert len(state["presets"]) >= 10
    finally:
        await core.stop()


async def test_ai_context_includes_vehicle(tmp_path):
    core = build_core(_cfg(tmp_path))
    await core.start()
    try:
        ctx = core.companion.build_context(core.hub, [])
        assert ctx["vehicle"] is not None
        assert ctx["vehicle"]["height_m"] > 2  # a tall van, from the default preset
    finally:
        await core.stop()
