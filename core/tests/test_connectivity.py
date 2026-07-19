"""Connectivity: the plugin's status entities + the weak-signal / offline advisor.
Connectivity is core van state (offline-first — never a dependency), so it exists
against the bare twin and the van stays usable with no signal (Rule 3)."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.notices import WeakSignal


@pytest.fixture
async def core(tmp_path):
    c = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, simulate=False, data_dir=tmp_path)
    )
    await c.start()
    yield c
    await c.stop()


async def test_connectivity_entities_registered(core):
    for eid in (
        "binary_sensor.internet", "sensor.signal_strength",
        "sensor.network_type", "binary_sensor.gps_fix",
    ):
        assert eid in core.hub.entities, eid
    assert core.hub.entities["sensor.signal_strength"].unit == "%"
    assert core.hub.entities["sensor.network_type"].state == "LTE"


async def test_entities_follow_signals(core):
    await core.twin.set_signal("connectivity.signal_pct", 12.0)
    assert core.hub.entities["sensor.signal_strength"].state == 12.0
    await core.twin.set_signal("connectivity.online", False)
    assert core.hub.entities["binary_sensor.internet"].state is False


# --- advisor -----------------------------------------------------------------

async def test_no_notice_with_good_signal(core):
    # Seeded online at 74% → nothing to say.
    assert WeakSignal(25.0).evaluate(core.hub) is None


async def test_weak_signal_notice(core):
    await core.twin.set_signal("connectivity.signal_pct", 12.0)
    n = WeakSignal(25.0).evaluate(core.hub)
    assert n is not None and n.key == "connectivity" and n.level == "info"
    assert "12%" in n.message


async def test_offline_notice_is_reassuring(core):
    await core.twin.set_signal("connectivity.online", False)
    n = WeakSignal(25.0).evaluate(core.hub)
    assert n is not None
    assert n.data["online"] is False
    # Offline-first framing: never implies the van has stopped working.
    assert "keeps running" in n.message.lower()


async def test_weak_signal_fires_through_engine(core):
    await core.twin.set_signal("connectivity.signal_pct", 5.0)
    keys = {n["key"] for n in core.advisors.active_notices()}
    assert "connectivity" in keys
    # Recovering clears it.
    await core.twin.set_signal("connectivity.signal_pct", 80.0)
    keys = {n["key"] for n in core.advisors.active_notices()}
    assert "connectivity" not in keys
