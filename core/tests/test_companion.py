"""Companion briefing — template (offline) and LLM-phrased paths."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config


class FakeClient:
    model = "fake"

    def __init__(self, text: str | None, available: bool = True) -> None:
        self._text = text
        self._available = available
        self.calls = 0
        self.last_system: str | None = None
        self.last_user: str | None = None

    async def available(self) -> bool:
        return self._available

    async def chat_json(self, system, user):  # pragma: no cover - unused here
        return None

    async def chat_text(self, system, user):
        self.calls += 1
        self.last_system = system
        self.last_user = user
        return self._text


def _force_llm(core, text):
    """Make the core's router active and return canned text via a fake client."""
    client = FakeClient(text)
    core.router._client_factory = lambda _b: client
    core.router._active = True
    return client


@pytest.fixture
async def core(tmp_path):
    c = build_core(Config(ai_enabled=False, weather_enabled=False, memory_enabled=False, data_dir=tmp_path))
    await c.start()
    yield c
    await c.stop()


async def test_template_briefing_mentions_notices(core):
    await core.twin.set_signal("fresh_water.level_pct", 8.0)
    text = await core.companion.briefing(
        core.hub, core.advisors.active_notices(), use_llm=False
    )
    assert "°C" in text
    assert "Fresh water" in text


async def test_llm_briefing_used_when_active(core):
    _force_llm(core, "Good morning! All systems are happy.")
    text = await core.companion.briefing(
        core.hub, core.advisors.active_notices(), use_llm=True
    )
    assert text == "Good morning! All systems are happy."


async def test_llm_failure_falls_back_to_template(core):
    client = _force_llm(core, None)  # model returns nothing
    text = await core.companion.briefing(
        core.hub, core.advisors.active_notices(), use_llm=True
    )
    assert client.calls == 1
    assert text  # non-empty template


async def test_context_includes_predictions(core):
    ctx = core.companion.build_context(core.hub, [])
    assert "predictions" in ctx and isinstance(ctx["predictions"], dict)
    # solar energy integral is always computed when telemetry is present
    assert "solar_wh_24h" in ctx["predictions"]


async def test_trip_absent_until_meaningful(core):
    # Fresh trip (0 km, 0 nights) → no journey recap to add.
    assert core.companion.build_context(core.hub, [])["trip"] is None


async def test_briefing_recaps_the_journey(core):
    start_odo = core.twin.get("vehicle.odometer_km")
    await core.twin.set_signal("vehicle.odometer_km", start_odo + 25.0)
    ctx = core.companion.build_context(core.hub, [])
    assert ctx["trip"] is not None and ctx["trip"]["distance_km"] == 25.0
    # Offline template surfaces it (Rule 3 — works with no model).
    text = await core.companion.briefing(core.hub, [], use_llm=False)
    assert "This trip" in text and "25 km" in text


def test_template_starts_with_greeting():
    from openvan_core.companion import Companion

    rendered = Companion(None).render_template({"greeting": "Good morning", "notices": []})
    assert rendered.startswith("Good morning.")


# --- resource-aware camp recommendation -------------------------------------

def test_camp_needs_flags_low_resources():
    from openvan_core.companion import _camp_needs

    ctx = {
        "fresh_water_pct": 12.0,
        "battery_soc_pct": 22.0,
        "grey_water_pct": 90.0,
        "diesel_pct": 15.0,
        "predictions": {},
    }
    needs = {n["resource"]: n for n in _camp_needs(ctx)}
    assert needs["fresh_water"]["amenity"] == "water"
    assert needs["battery"]["amenity"] == "power"
    assert needs["grey_water"]["amenity"] == "toilets"
    assert "diesel" in needs  # low fuel flagged even without an amenity to fix it


def test_camp_needs_quiet_when_healthy():
    from openvan_core.companion import _camp_needs

    ctx = {
        "fresh_water_pct": 80.0,
        "battery_soc_pct": 85.0,
        "grey_water_pct": 20.0,
        "diesel_pct": 70.0,
        "predictions": {},
    }
    assert _camp_needs(ctx) == []


_SPOTS = [
    {"name": "Dry Ridge", "distance_km": 1.0, "amenities": ["view"]},
    {"name": "Lakeside", "distance_km": 4.0, "amenities": ["water", "toilets"]},
]


async def test_camp_recommendation_feeds_low_water_to_the_model(core):
    import json

    client = _force_llm(core, "Since we're low on water, Lakeside has a tap.")
    await core.twin.set_signal("fresh_water.level_pct", 12.0)
    reply = await core.companion.recommend_camp(
        core.hub, core.advisors.active_notices(), _SPOTS, wants=[], use_llm=True
    )
    assert reply  # the model's phrasing is returned
    payload = json.loads(client.last_user)
    # The model was actually told water is low and given the full resource status.
    resources = {n["resource"] for n in payload["needs"]}
    assert "fresh_water" in resources
    assert payload["status"]["fresh_water_pct"] == 12.0
    assert "grey_water_pct" in payload["status"]


async def test_camp_offline_fallback_surfaces_a_spot_that_covers_the_need(core):
    await core.twin.set_signal("fresh_water.level_pct", 12.0)
    reply = await core.companion.recommend_camp(
        core.hub, core.advisors.active_notices(), _SPOTS, wants=[], use_llm=False
    )
    # Offline, still points at the spot with water and flags the need.
    assert "Lakeside" in reply
    assert "water" in reply.lower()
