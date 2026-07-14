"""Focused unit tests for the primitive building blocks."""

from __future__ import annotations

import pytest

from openvan_core.entities import Entity
from openvan_core.events import EventBus
from openvan_core.hub import Hub
from openvan_core.intents import Intent, IntentResolver
from openvan_core.safety import CriticalBatteryLoadShedding, SafetyValidator
from openvan_core.twin import VanTwin


async def test_event_bus_delivers_and_unsubscribes():
    bus = EventBus()
    seen = []

    async def handler(event):
        seen.append(event.data.get("n"))

    unsubscribe = bus.subscribe("tick", handler)
    await bus.publish("tick", {"n": 1})
    unsubscribe()
    await bus.publish("tick", {"n": 2})
    assert seen == [1]


async def test_twin_only_emits_on_change():
    bus = EventBus()
    twin = VanTwin(bus)
    changes = []

    async def on_change(event):
        changes.append(event.data["value"])

    bus.subscribe("twin.signal_changed", on_change)
    await twin.set_signal("x", 1)
    await twin.set_signal("x", 1)  # no change -> no event
    await twin.set_signal("x", 2)
    assert changes == [1, 2]


async def test_intent_resolver_picks_off_command():
    resolver = IntentResolver()
    entities = {
        "light.cabin": Entity(
            "light.cabin", "Cabin Light", "light", "lighting",
            controllable=True, commands=["turn_on", "turn_off"],
        )
    }
    intent = await resolver.resolve("turn off the cabin light", entities)
    assert intent is not None
    assert intent.command == "turn_off"


async def test_safety_validator_allows_when_soc_healthy():
    bus = EventBus()
    twin = VanTwin(bus)
    hub = Hub(bus, twin, SafetyValidator([CriticalBatteryLoadShedding()]))
    await hub.register_entity(
        Entity("sensor.house_battery_soc", "SOC", "sensor", "energy", state=80.0)
    )
    await hub.register_entity(
        Entity(
            "light.cabin", "Cabin Light", "light", "lighting",
            controllable=True, commands=["turn_on", "turn_off"],
            attributes={"essential": False},
        ),
        handler=_record_handler([]),
    )
    decision = await hub.safety.check(Intent("light.cabin", "turn_on"), hub)
    assert decision.allowed


def _record_handler(sink):
    async def handler(command, params):
        sink.append((command, params))

    return handler
