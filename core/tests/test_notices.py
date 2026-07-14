"""Proactive advisor notices against the simulated van."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config


@pytest.fixture
async def core():
    c = build_core(Config(ai_enabled=False, telemetry_enabled=False))
    await c.start()
    yield c
    await c.stop()


def _keys(core):
    return {n["key"] for n in core.advisors.active_notices()}


async def test_no_notices_on_healthy_defaults(core):
    # Seeded state is comfortable — nothing to nag about.
    assert _keys(core) == set()


async def test_low_fresh_water_creates_and_clears(core):
    events = []
    core.bus.subscribe("notice.created", _collect(events, "created"))
    core.bus.subscribe("notice.cleared", _collect(events, "cleared"))

    await core.twin.set_signal("fresh_water.level_pct", 8.0)
    assert "fresh_water_low" in _keys(core)
    assert ("created", "fresh_water_low") in events

    # Refill — the notice clears (edge-triggered).
    await core.twin.set_signal("fresh_water.level_pct", 60.0)
    assert "fresh_water_low" not in _keys(core)
    assert ("cleared", "fresh_water_low") in events


async def test_notice_not_re_emitted_while_condition_holds(core):
    created = []
    core.bus.subscribe("notice.created", _collect(created, "created"))
    await core.twin.set_signal("fresh_water.level_pct", 10.0)
    await core.twin.set_signal("fresh_water.level_pct", 9.0)
    await core.twin.set_signal("fresh_water.level_pct", 8.0)
    # Still low the whole time — created exactly once.
    assert created.count(("created", "fresh_water_low")) == 1


async def test_grey_tank_full_notice(core):
    await core.twin.set_signal("grey_water.level_pct", 92.0)
    assert "grey_water_full" in _keys(core)


async def test_battery_runtime_warns_at_high_draw(core):
    # Low SoC + heavy discharge -> short runtime -> warning.
    await core.twin.set_signal("house_battery.current", -40.0)
    await core.twin.set_signal("house_battery.soc", 20.0)
    assert "battery_runtime_low" in _keys(core)


def _collect(sink, label):
    async def handler(event):
        sink.append((label, event.data["notice"]["key"]))

    return handler
