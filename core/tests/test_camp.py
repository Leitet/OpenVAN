"""Camp sources + the camp service (aggregate / dedup / rank / cache)."""

from __future__ import annotations

from openvan_core import build_core
from openvan_core.camp import CampService
from openvan_core.config import Config
from openvan_core.runtime import _looks_like_camp_query


def test_camp_query_detector_avoids_false_positives():
    assert _looks_like_camp_query("where should we sleep tonight?")
    assert _looks_like_camp_query("find a campsite nearby")
    assert _looks_like_camp_query("somewhere sheltered to camp for the night")
    assert _looks_like_camp_query("var ska vi sova i natt?")  # Swedish
    # Not camp queries — must not hijack these:
    assert not _looks_like_camp_query("how's the campervan doing?")
    assert not _looks_like_camp_query("turn on the cabin light")
    assert not _looks_like_camp_query("will the battery last?")


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
    # A proprietary keyed source registers the same way, disabled + needs a key.
    assert infos["park4night"]["requires_key"] is True
    assert infos["park4night"]["enabled"] is False


async def test_keyed_source_unavailable_without_key_and_parses(tmp_path, monkeypatch):
    _service(tmp_path)  # puts campsources/ on sys.path and imports the packages
    import park4night

    monkeypatch.delenv("OPENVAN_PARK4NIGHT_KEY", raising=False)
    monkeypatch.delenv("OPENVAN_PARK4NIGHT_URL", raising=False)
    src = park4night.Park4NightSource()
    assert await src.available() is False
    assert await src.search(46.5, 11.3, 20) == []  # no key -> nothing, no crash

    spots = park4night.Park4NightSource._parse(
        {"places": [{"id": 7, "name": "Wild Bay", "lat": 46.6, "lng": 11.7, "type": "wild", "services": ["water"]}]},
        20,
    )
    assert len(spots) == 1
    assert spots[0].name == "Wild Bay" and spots[0].kind == "wild"
    assert spots[0].amenities == ["water"]


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


class _FakeCampLLM:
    """A model that routes a camp query to find_camp, then recommends a spot."""

    async def available(self):
        return True

    async def chat_json(self, system, user):
        return '{"find_camp": {"radius_km": 20, "wants": ["sheltered"]}}'

    async def chat_text(self, system, user):
        return "Head to Pine Forest Aire, 2.7 km away — the north pines will shelter you."


async def test_chat_proposes_a_camp_spot(tmp_path):
    core = build_core(
        Config(
            ai_enabled=True,
            weather_enabled=False,
            memory_enabled=False,
            telemetry_enabled=False,
            data_dir=tmp_path,
        )
    )
    core.router._client_factory = lambda _b: _FakeCampLLM()
    await core.start()
    await core.twin.set_signal("gps.lat", 46.5, source="test")
    await core.twin.set_signal("gps.lon", 11.3, source="test")

    r = await core.chat("where should we sleep tonight?")
    assert r["action"] is False
    assert r["ok"] is True
    assert len(r["spots"]) >= 3  # sim source returned candidates
    assert "Pine Forest" in r["reply"]  # the van recommended one
    await core.stop()


async def test_offline_camp_query_routes_to_camp_not_a_command(tmp_path):
    # No model at all: the keyword guard still routes a camp query to a search and
    # a localised list — never to a device command.
    core = build_core(
        Config(
            ai_enabled=False,
            weather_enabled=False,
            memory_enabled=False,
            telemetry_enabled=False,
            data_dir=tmp_path,
        )
    )
    await core.start()
    await core.twin.set_signal("gps.lat", 46.5, source="test")
    await core.twin.set_signal("gps.lon", 11.3, source="test")

    r = await core.chat("where should we sleep tonight?")
    assert r["action"] is False
    assert len(r["spots"]) >= 3
    assert "Nearby I found" in r["reply"]  # offline localised list
    await core.stop()
