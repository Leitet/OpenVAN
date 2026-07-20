"""Low-clearance / weight-limit routing warnings, checked against the vehicle."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config
from openvan_core.notices import LowClearance, OverweightRoad
from openvan_core.roads import RoadNetwork, _parse_limit


def _cfg(tmp_path, vehicle=None):
    kw = {}
    if vehicle is not None:
        kw["vehicle"] = vehicle
    return Config(
        ai_enabled=False, weather_enabled=False, memory_enabled=False,
        telemetry_enabled=False, data_dir=tmp_path, **kw,
    )


def test_parse_limit():
    assert _parse_limit("3.5") == 3.5
    assert _parse_limit("3.5 m") == 3.5
    assert _parse_limit("7.5 t") == 7.5
    assert _parse_limit(None) is None
    assert _parse_limit("3'6\"") is None  # feet/inches → skip


@pytest.fixture
async def core(tmp_path):
    # A 2.76 m tall, 3.5 t gross van (Jumper L4H3-ish).
    c = build_core(_cfg(tmp_path, vehicle={"height_mm": 2764, "gross_weight_kg": 3500}))
    await c.start()
    yield c
    await c.stop()


async def test_low_clearance_fires_when_bridge_too_low(core):
    await core.twin.set_signal("road.max_height_m", 3.5)  # plenty
    assert LowClearance(core.config).evaluate(core.hub) is None
    await core.twin.set_signal("road.max_height_m", 2.9)  # within 0.2 m margin
    n = LowClearance(core.config).evaluate(core.hub)
    assert n is not None and n.data["wont_fit"] is False
    await core.twin.set_signal("road.max_height_m", 2.5)  # below the van
    n = LowClearance(core.config).evaluate(core.hub)
    assert n.data["wont_fit"] is True and "won't fit" in n.message


async def test_weight_limit_fires_when_over(core):
    await core.twin.set_signal("road.max_weight_t", 7.5)
    assert OverweightRoad(core.config).evaluate(core.hub) is None
    await core.twin.set_signal("road.max_weight_t", 3.0)  # van is 3.5 t
    n = OverweightRoad(core.config).evaluate(core.hub)
    assert n is not None and "3.5 t" in n.message


async def test_no_limit_or_no_vehicle_is_quiet(core):
    await core.twin.set_signal("road.max_height_m", 0)  # 0 = no limit
    assert LowClearance(core.config).evaluate(core.hub) is None
    # No vehicle height → can't judge, stay quiet.
    empty = LowClearance(None)
    await core.twin.set_signal("road.max_height_m", 2.0)
    assert empty.evaluate(core.hub) is None


async def test_limits_surface_as_live_notices(core):
    await core.twin.set_signal("road.max_height_m", 2.4)
    await core.twin.set_signal("road.max_weight_t", 3.0)
    keys = {n["key"] for n in core.advisors.active_notices()}
    assert "low_clearance" in keys and "weight_limit" in keys


def test_road_restriction_lookahead(tmp_path):
    net = RoadNetwork(Config(data_dir=tmp_path))
    # A little chain 1-2-3-4 with a 2.8 m bridge on segment 2-3.
    net._ingest([
        {"type": "way", "nodes": [1, 2, 3, 4],
         "geometry": [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 0.001},
                      {"lat": 0, "lon": 0.002}, {"lat": 0, "lon": 0.003}],
         "tags": {"maxheight": "2.8"}},
    ])
    net._prev, net._cur = 1, 2  # driving toward the bridge
    ahead = net.restriction_ahead()
    assert ahead["maxheight"] == 2.8


async def test_narrow_road_advisor(core):
    from openvan_core.notices import NarrowRoad

    # The fixture's profile has no width — give it one (incl. mirrors).
    core.config.vehicle["width_mirrors_mm"] = 2350
    # A 2.0 m limit is too tight for a 2.35 m van.
    await core.twin.set_signal("road.max_width_m", 2.0)
    notice = NarrowRoad(core.config).evaluate(core.hub)
    assert notice is not None and "Narrow road" in notice.title
    # Wide enough limit → quiet.
    await core.twin.set_signal("road.max_width_m", 3.5)
    assert NarrowRoad(core.config).evaluate(core.hub) is None
    # No limit → quiet.
    await core.twin.set_signal("road.max_width_m", 0.0)
    assert NarrowRoad(core.config).evaluate(core.hub) is None
