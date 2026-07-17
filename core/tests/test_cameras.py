"""Security cameras: entity model from twin signals + camera→intrusion link."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.notices import Intrusion


@pytest.fixture
async def core(tmp_path):
    c = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, data_dir=tmp_path)
    )
    await c.start()
    yield c
    await c.stop()


async def test_cameras_registered(core):
    for cam in ("rear", "cabin", "entry", "awning"):
        e = core.hub.entities[f"camera.{cam}"]
        assert e.domain == "camera" and e.category == "security"
        assert e.state == "online"
    assert core.hub.entities["camera.awning"].attributes["connection"] == "4g"
    assert core.hub.entities["camera.rear"].attributes["connection"] == "wired"


async def test_camera_signals_update_entity(core):
    await core.twin.set_signal("camera.cabin.motion", True, source="test")
    assert core.hub.entities["camera.cabin"].attributes["motion"] is True
    await core.twin.set_signal("camera.cabin.recording", True, source="test")
    assert core.hub.entities["camera.cabin"].attributes["recording"] is True
    await core.twin.set_signal("camera.cabin.online", False, source="test")
    assert core.hub.entities["camera.cabin"].state == "offline"


async def test_camera_motion_trips_intrusion_when_armed(core):
    await core.twin.set_signal("camera.entry.motion", True)
    # Disarmed → cameras just record, no alert.
    assert Intrusion(core.security).evaluate(core.hub) is None
    core.security.arm()
    n = Intrusion(core.security).evaluate(core.hub)
    assert n is not None
    assert n.data["camera"] == "entry"
    assert "entry camera" in n.message


async def test_disarmed_cameras_do_not_alert(core):
    await core.set_security_armed(True)
    await core.twin.set_signal("camera.rear.motion", True)
    assert "intrusion" in {x["key"] for x in core.advisors.active_notices()}
    await core.set_security_armed(False)
    assert "intrusion" not in {x["key"] for x in core.advisors.active_notices()}


async def test_add_and_remove_camera(core):
    ids = {c["id"] for c in core.cameras()}
    assert ids == {"rear", "cabin", "entry", "awning"}

    # Add a new one — entity appears with the given attributes + seeded online.
    assert await core.add_camera("garage", "Garage", "door", "wired") is True
    assert core.hub.entities["camera.garage"].attributes["connection"] == "wired"
    assert core.hub.entities["camera.garage"].state == "online"
    assert "garage" in {c["id"] for c in core.cameras()}
    # Duplicate id is rejected.
    assert await core.add_camera("garage", "x", "door", "wifi") is False

    # Remove one — the entity is gone and it's dropped from the list.
    assert await core.remove_camera("cabin") is True
    assert "camera.cabin" not in core.hub.entities
    assert "cabin" not in {c["id"] for c in core.cameras()}
    assert await core.remove_camera("nope") is False


async def test_removed_camera_cannot_trip_intrusion(core):
    await core.remove_camera("rear")
    await core.set_security_armed(True)
    # The removed camera's motion signal is quieted; re-asserting it must not alarm.
    await core.twin.set_signal("camera.rear.motion", True)
    assert "intrusion" not in {x["key"] for x in core.advisors.active_notices()}


async def test_camera_list_persists_to_store(core):
    await core.add_camera("garage", "Garage", "door", "wired")
    saved = core.store.get_all("plugin:cameras").get("list")
    assert any(c["id"] == "garage" for c in saved)
