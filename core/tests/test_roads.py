"""Road-following: the sim snaps driving onto the real road graph.

These build the graph in-memory (no Overpass / network) and exercise the pure
advance/junction logic, plus the simulation's road-vs-dead-reckon choice.
"""

from __future__ import annotations

from collections import defaultdict

from openvan_core.config import Config
from openvan_core.events import EventBus
from openvan_core.roads import RoadNetwork, _bearing, _haversine_m
from openvan_core.simulation import VanSimulation
from openvan_core.twin import VanTwin


def _grid_network(tmp_path) -> RoadNetwork:
    """A tiny plus-shaped junction at node 0 (origin), with arms N/E/S/W.

        1(N)
        |
    4(W)-0-2(E)
        |
        3(S)
    """
    net = RoadNetwork(Config(data_dir=tmp_path))
    d = 0.01  # ~1.1 km arms
    net.nodes = {
        0: (0.0, 0.0),
        1: (d, 0.0),  # north
        2: (0.0, d),  # east
        3: (-d, 0.0),  # south
        4: (0.0, -d),  # west
    }
    adj = defaultdict(set)
    for n in (1, 2, 3, 4):
        adj[0].add(n)
        adj[n].add(0)
    net.adj = adj
    net._center = (0.0, 0.0)
    return net


def test_bearing_cardinals():
    assert abs(_bearing((0, 0), (1, 0)) - 0) < 1  # north
    assert abs(_bearing((0, 0), (0, 1)) - 90) < 1  # east
    assert abs(_bearing((0, 0), (-1, 0)) - 180) < 1  # south


def test_advance_follows_a_straight_arm(tmp_path):
    net = _grid_network(tmp_path)
    # Start just south of the junction, heading north → should track up the N arm.
    net._snap(-0.005, 0.0, heading=0.0)
    lat, lon, hdg = net.advance(-0.005, 0.0, 0.0, dist_m=200)
    assert lon == 0.0  # stayed on the north–south line
    assert lat > -0.005  # moved north
    assert abs(hdg - 0.0) < 1 or abs(hdg - 360.0) < 1


def test_junction_choice_follows_driver_heading(tmp_path):
    net = _grid_network(tmp_path)
    # On the west arm (node 4 → 0), driving east. Each arm is ~1.1 km, so 1.5 km
    # carries us through the junction and onto the chosen arm.
    net._prev, net._cur, net._progress_m = 4, 0, 0.0
    # Driver holds a northerly heading through the junction → should take the N arm.
    lat, lon, hdg = net.advance(0.0, -0.005, heading=0.0, dist_m=1500)
    assert lat > 0.0 and abs(lon) < 1e-6  # went north up the N arm
    assert net._cur == 1

    net2 = _grid_network(tmp_path)
    net2._prev, net2._cur, net2._progress_m = 4, 0, 0.0
    # Same approach but the driver wants to continue east → takes the E arm.
    lat2, lon2, _ = net2.advance(0.0, -0.005, heading=90.0, dist_m=1500)
    assert lon2 > 0.0 and abs(lat2) < 1e-6
    assert net2._cur == 2


def test_advance_returns_none_without_a_graph(tmp_path):
    net = RoadNetwork(Config(data_dir=tmp_path))  # empty, and no loop to fetch
    assert net.advance(46.5, 11.3, 0.0, dist_m=100) is None


async def test_simulation_snaps_driving_to_roads(tmp_path):
    net = _grid_network(tmp_path)
    bus = EventBus()
    twin = VanTwin(bus)
    sim = VanSimulation(bus, twin, roads=net)
    # Sit on the west arm, driving east toward the junction, wanting to go north.
    await twin.set_signal("gps.lat", 0.0)
    await twin.set_signal("gps.lon", -0.005)
    await twin.set_signal("vehicle.ignition", True)
    await twin.set_signal("vehicle.speed_kmh", 120.0)
    await twin.set_signal("vehicle.heading", 0.0)  # north

    # 120 km/h × 1 s × 15 ≈ 500 m — snaps to the junction and heads up the ~1.1 km
    # north arm, stopping short of the dead-end (which would U-turn).
    for _ in range(15):
        await sim.step(1.0)

    lat = twin.get("gps.lat")
    lon = twin.get("gps.lon")
    # Snapped to the graph: still on a road line, not dead-reckoned diagonally.
    assert lat > 0.0  # made it up the north arm
    assert abs(lon) < 1e-4  # hugged the N–S road, not a straight NE line


async def test_simulation_dead_reckons_without_roads(tmp_path):
    bus = EventBus()
    twin = VanTwin(bus)
    sim = VanSimulation(bus, twin, roads=None)
    await twin.set_signal("gps.lat", 46.5)
    await twin.set_signal("gps.lon", 11.3)
    await twin.set_signal("vehicle.ignition", True)
    await twin.set_signal("vehicle.speed_kmh", 90.0)
    await twin.set_signal("vehicle.heading", 90.0)  # due east
    await sim.step(10.0)
    assert twin.get("gps.lon") > 11.3  # moved east by free dead reckoning
    assert abs(twin.get("gps.lat") - 46.5) < 1e-6  # latitude unchanged heading east


def test_haversine_sanity():
    assert 1000 < _haversine_m((0.0, 0.0), (0.0, 0.01)) < 1200  # ~1.11 km per 0.01°
