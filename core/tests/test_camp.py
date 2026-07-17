"""Camp sources + the camp service (aggregate / dedup / rank / cache)."""

from __future__ import annotations

from openvan_core.camp import CampService
from openvan_core.config import Config


def _service(tmp_path, sources=("sim",), lat=46.5, lon=11.3):
    cfg = Config(data_dir=tmp_path)
    cfg.camp_sources = list(sources)
    svc = CampService(cfg, get_location=lambda: (lat, lon))
    svc.discover()  # imports campsources/ packages (sim, overpass) and registers them
    return svc, cfg


async def test_sim_source_returns_ranked_spots_near_location(tmp_path):
    svc, _ = _service(tmp_path)
    res = await svc.search()
    spots = res["spots"]
    assert len(spots) >= 3
    assert all(s["source"] == "sim" for s in spots)
    dists = [s["distance_km"] for s in spots]
    assert dists == sorted(dists)  # ranked nearest-first
    assert all(d <= res["radius_km"] for d in dists)
    assert res["location"] == {"lat": 46.5, "lon": 11.3}
    # spots carry usable detail for the assistant to reason about.
    assert any(s["description"] for s in spots)


async def test_no_enabled_source_yields_no_spots(tmp_path):
    svc, _ = _service(tmp_path, sources=())
    res = await svc.search()
    assert res["spots"] == []


def test_source_infos_lists_registered_with_enabled_flag(tmp_path):
    svc, _ = _service(tmp_path)
    infos = {i["id"]: i for i in svc.source_infos()}
    assert infos["sim"]["enabled"] is True
    assert infos["sim"]["requires_internet"] is False
    assert "overpass" in infos and infos["overpass"]["enabled"] is False
    assert infos["overpass"]["requires_internet"] is True


async def test_offline_without_location_serves_cache(tmp_path):
    svc, _ = _service(tmp_path)
    await svc.search()  # populates + persists the cache
    svc.get_location = lambda: (None, None)
    res = await svc.search()
    assert res["location"] is None
    assert len(res["spots"]) >= 3  # served from cache


def test_set_enabled_toggles_and_persists_to_config(tmp_path):
    svc, cfg = _service(tmp_path, sources=("sim",))
    assert svc.set_enabled("overpass", True) is True
    assert "overpass" in cfg.camp_sources
    assert svc.set_enabled("overpass", False) is True
    assert "overpass" not in cfg.camp_sources
    assert svc.set_enabled("nonexistent", True) is False


async def test_radius_filters_out_distant_spots(tmp_path):
    # A tiny radius keeps only the closest sim spots.
    svc, _ = _service(tmp_path)
    wide = await svc.search(radius_km=30)
    narrow = await svc.search(radius_km=2)
    assert len(narrow["spots"]) < len(wide["spots"])
