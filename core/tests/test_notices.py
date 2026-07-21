"""Proactive advisor notices against the simulated van."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config


@pytest.fixture
async def core():
    c = build_core(Config(ai_enabled=False, weather_enabled=False, memory_enabled=False, telemetry_enabled=False))
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


async def test_one_failing_advisor_does_not_stop_the_others():
    """A raising advisor must not prevent the rest (some are life-critical) from
    evaluating — the engine isolates each."""
    from openvan_core.events import EventBus
    from openvan_core.notices import Advisor, AdvisorEngine, Notice

    class _Boom(Advisor):
        key = "boom"

        def evaluate(self, hub):
            raise RuntimeError("kaboom")

    class _Ok(Advisor):
        key = "ok"

        def evaluate(self, hub):
            return Notice("ok", "info", "energy", "Ok", "still here", {})

    engine = AdvisorEngine(EventBus(), hub=None, advisors=[_Boom(), _Ok()])
    await engine.evaluate()
    assert "ok" in {n["key"] for n in engine.active_notices()}


def _collect(sink, label):
    async def handler(event):
        sink.append((label, event.data["notice"]["key"]))

    return handler


# --- snooze / acknowledge ----------------------------------------------------

import time as _time

from openvan_core import build_core
from openvan_core.config import Config


@pytest.fixture
async def live_core(tmp_path):
    c = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, data_dir=tmp_path)
    )
    await c.start()
    yield c
    await c.stop()


async def test_acknowledge_hides_until_it_fires_again(live_core):
    core = live_core
    await core.twin.set_signal("fresh_water.level_pct", 5.0)
    assert "fresh_water_low" in {n["key"] for n in core.advisors.active_notices()}

    assert await core.advisors.acknowledge("fresh_water_low") is True
    assert "fresh_water_low" not in {n["key"] for n in core.advisors.active_notices()}
    # Still firing → still hidden.
    await core.twin.set_signal("fresh_water.level_pct", 4.0)
    assert "fresh_water_low" not in {n["key"] for n in core.advisors.active_notices()}
    # Condition clears → the ack is spent; the NEXT occurrence shows again.
    await core.twin.set_signal("fresh_water.level_pct", 80.0)
    await core.twin.set_signal("fresh_water.level_pct", 5.0)
    assert "fresh_water_low" in {n["key"] for n in core.advisors.active_notices()}


async def test_snooze_hides_for_a_while_then_reannounces(live_core, monkeypatch):
    core = live_core
    events: list[tuple[str, str]] = []

    async def on_created(e):
        events.append(("created", e.data["notice"]["key"]))

    core.bus.subscribe("notice.created", on_created)
    await core.twin.set_signal("grey_water.level_pct", 95.0)
    assert "grey_water_full" in {n["key"] for n in core.advisors.active_notices()}

    assert await core.advisors.snooze("grey_water_full", hours=1.0) is True
    assert "grey_water_full" not in {n["key"] for n in core.advisors.active_notices()}
    # Snooze survives a clear (unlike ack): still hidden while snoozed.
    events.clear()
    # Fast-forward the wall clock past the snooze.
    real = _time.time()
    import openvan_core.notices as notices_mod
    monkeypatch.setattr(notices_mod.time, "time", lambda: real + 2 * 3600)
    await core.advisors.evaluate()
    assert "grey_water_full" in {n["key"] for n in core.advisors.active_notices()}
    assert ("created", "grey_water_full") in events  # re-announced to the UI


async def test_dispositions_persist_across_restart(live_core, tmp_path):
    core = live_core
    await core.twin.set_signal("fresh_water.level_pct", 5.0)
    await core.advisors.snooze("fresh_water_low", hours=8.0)

    fresh = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, data_dir=tmp_path)
    )
    await fresh.start()
    try:
        await fresh.twin.set_signal("fresh_water.level_pct", 5.0)
        assert "fresh_water_low" not in {n["key"] for n in fresh.advisors.active_notices()}
    finally:
        await fresh.stop()
