"""Security away-mode: arm/disarm + intrusion advisor."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.notices import Intrusion
from openvan_core.security import SecuritySystem


def test_arm_disarm_defaults_disarmed():
    s = SecuritySystem()
    assert s.is_armed() is False
    s.arm()
    assert s.is_armed() is True
    s.disarm()
    assert s.is_armed() is False


@pytest.fixture
async def core(tmp_path):
    c = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, data_dir=tmp_path)
    )
    await c.start()
    yield c
    await c.stop()


async def test_intrusion_only_fires_when_armed(core):
    await core.twin.set_signal("security.door_open", True)
    # Disarmed → a door opening is normal, no alert.
    assert Intrusion(core.security).evaluate(core.hub) is None
    # Armed → the same event is an intrusion.
    core.security.arm()
    n = Intrusion(core.security).evaluate(core.hub)
    assert n is not None and n.category == "safety"
    assert n.data["door"] is True


async def test_set_armed_updates_notices_live(core):
    await core.twin.set_signal("security.motion", True)
    await core.set_security_armed(True)
    keys = {x["key"] for x in core.advisors.active_notices()}
    assert "intrusion" in keys
    await core.set_security_armed(False)
    keys = {x["key"] for x in core.advisors.active_notices()}
    assert "intrusion" not in keys  # disarming clears it
