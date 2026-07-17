"""The companion voice — warm, proactive briefings.

Turns the van's live state (and any active notices) into a short, friendly
spoken-style briefing: "Good morning. It's 4°C outside and the cabin's a cosy
20°. Battery's good for about two more days, but fresh water is getting low —
want me to find a refill?"

Offline-first: a deterministic template always works. When a local LLM is
available it phrases the same facts more naturally (model-agnostic; the model
only rewords facts we give it — it never invents data or controls anything).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .llm import build_system
from .predictions import compute_predictions

if TYPE_CHECKING:  # pragma: no cover
    from .hub import Hub
    from .llm import ModelRouter
    from .memory import TravelMemory
    from .telemetry import TelemetryStore
    from .weather import WeatherService

BRIEFING_SYSTEM = """\
Your task: given your current status as JSON, write a short, friendly spoken briefing
of 2-4 sentences about how YOU are doing, in the first person ("I'm at 82%…"). Greet
by time of day. Mention only what is relevant or noteworthy (especially anything in
`notices`). Never invent data beyond what is given. Plain natural speech — no lists,
no markdown, no headings.
"""

# Localised deterministic reply for when no model can generate (offline, or the
# configured model failed). Follows the assistant language (Config.language).
_ANSWER_FALLBACK = {
    "en": 'I can report status and run direct commands like "turn on the cabin light", '
    "but I can't reach a model to chat freely right now.",
    "sv": 'Jag kan visa status och köra direkta kommandon som "tänd kupébelysningen", '
    "men jag når ingen modell för att chatta fritt just nu.",
    "de": "Ich kann den Status anzeigen und direkte Befehle wie „Kabinenlicht "
    "einschalten“ ausführen, aber ich erreiche gerade kein Modell zum freien Chatten.",
}

ANSWER_SYSTEM = """\
Your task: you are chatting with the traveller. You are given your current status as
JSON, their message, and their durable `preferences` (how they like things). Answer
directly and briefly (1-3 sentences) about YOURSELF, in the first person ("my battery
is …", "I'm …"), using only facts from the status — if it isn't there, say you don't
have it. Give friendly, practical suggestions, and lean on their preferences when
relevant. You do NOT control anything in this reply; if they want an action, tell them
to ask for it directly (e.g. "turn on the cabin light"). Plain natural speech — no
lists, no markdown.
"""

CAMP_SYSTEM = """\
Your task: recommend where to spend the night, choosing from the `spots` I found
nearby. Each spot has name, kind, distance_km, amenities and a description. You also
get `weather` (wind_from = the direction the wind blows FROM, wind_kmh, cloud,
condition, rain_eta_hours), `sun` (the hour now; the sun sets in the WEST),
`status` (my resources: battery %, fresh water %, grey water %, diesel %, and the
estimated hours until each runs out or fills up), `needs` (the resources running
low right now — each names the `amenity` that would solve it), `notices` (active
alerts), `wants` (what they asked for this time) and `preferences` (durable likings
I've learned — e.g. "prefers quiet spots away from roads", "wants morning sun").

Honour their `request`, `wants` and standing `preferences`, and FACTOR IN MY `needs`: when a resource is
low, prefer a spot whose `amenities` meet it (water / power / toilets for a grey
dump) and say so — e.g. "since we're low on water, Lakeside has a tap". If no
nearby spot covers a need, suggest topping up on the way — e.g. "fill up at services
on the way to Z" or "grab diesel en route". Pick the best 1-2 spots and say why, in
the FIRST PERSON, warm and brief (2-4 sentences). Weigh distance, amenities, my
needs, rain and comfort. Where you can, add a short MICRO-SITING tip for the pitch:
for evening sun, face/park open to the WEST; for shelter, keep the side facing the
wind (`wind_from`) blocked by trees, walls or terrain, and avoid exposed ridges when
it's windy. Use only the facts given (spots, status, weather). No lists, no markdown.
"""

# Localised offline lines when no model can phrase a recommendation.
_CAMP_FALLBACK = {
    "en": "Nearby I found: {spots}.",
    "sv": "I närheten hittade jag: {spots}.",
    "de": "In der Nähe habe ich gefunden: {spots}.",
}
_CAMP_NONE = {
    "en": "I couldn't find any spots nearby right now.",
    "sv": "Jag hittade inga platser i närheten just nu.",
    "de": "Ich habe gerade keine Plätze in der Nähe gefunden.",
}
# Offline need hint: surface a nearby spot that covers a low resource.
_CAMP_NEED_HINT = {
    "en": " We're low on {resource} — {spot} has {amenity}.",
    "sv": " Vi har ont om {resource} — {spot} har {amenity}.",
    "de": " Wir haben wenig {resource} — {spot} bietet {amenity}.",
}
_NEED_WORD = {
    "en": {"fresh_water": "water", "battery": "power", "grey_water": "tank space", "diesel": "fuel"},
    "sv": {"fresh_water": "vatten", "battery": "ström", "grey_water": "tankutrymme", "diesel": "bränsle"},
    "de": {"fresh_water": "Wasser", "battery": "Strom", "grey_water": "Tankplatz", "diesel": "Kraftstoff"},
}
_AMENITY_WORD = {
    "en": {"water": "water", "power": "power", "toilets": "a dump/toilets"},
    "sv": {"water": "vatten", "power": "ström", "toilets": "toalett/tömning"},
    "de": {"water": "Wasser", "power": "Strom", "toilets": "Toiletten/Entsorgung"},
}

_BATTERY_CAPACITY_AH = 200.0


def _greeting(hour: int) -> str:
    if hour < 5:
        return "You're up late"
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


class Companion:
    def __init__(
        self,
        router: "ModelRouter",
        telemetry: "TelemetryStore | None" = None,
        weather: "WeatherService | None" = None,
        memory: "TravelMemory | None" = None,
    ) -> None:
        self.router = router
        self.telemetry = telemetry
        self.weather = weather
        self.memory = memory

    def build_context(
        self, hub: "Hub", notices: list[dict[str, Any]], *, hour: int | None = None
    ) -> dict[str, Any]:
        twin = hub.twin
        if hour is None:
            hour = _local_hour(twin)

        soc = _num(twin.get("house_battery.soc"))
        current = _num(twin.get("house_battery.current"))
        battery_days = None
        if soc is not None and current is not None and current < -0.05:
            battery_days = round(
                _BATTERY_CAPACITY_AH * (soc / 100.0) / abs(current) / 24.0, 1
            )

        # Predictions from actual recent history, not just instantaneous readings,
        # plus a weather-aware solar forecast when a forecast is available.
        predictions = compute_predictions(
            twin,
            self.telemetry,
            weather=self.weather.snapshot() if self.weather is not None else None,
        )
        battery_trend = predictions.get("battery_rate_pct_per_hour")

        weather = self.weather.snapshot() if self.weather is not None else {}

        recent_stays = []
        if self.memory is not None:
            for s in self.memory.list_stays(3):
                recent_stays.append(
                    {
                        "place": s.get("place"),
                        "lat": s.get("lat"),
                        "lon": s.get("lon"),
                        "nights": round((s.get("duration_hours") or 0) / 24.0, 1),
                        "condition": s.get("condition"),
                        "notes": s.get("notes"),
                    }
                )

        return {
            "recent_stays": recent_stays,
            "weather": {
                "condition": (weather.get("current") or {}).get("condition"),
                "outside_temp_c": (weather.get("current") or {}).get("temp_c"),
                "rain_eta_hours": weather.get("rain_eta_hours"),
            }
            if weather
            else None,
            "hour": hour,
            "greeting": _greeting(hour),
            "outside_temp_c": _num(twin.get("outside.temperature")),
            "cabin_temp_c": _num(twin.get("cabin.temperature")),
            "battery_soc_pct": soc,
            "battery_days_left": battery_days,
            "battery_trend_pct_per_hour": battery_trend,
            "predictions": predictions,
            "fresh_water_pct": _num(twin.get("fresh_water.level_pct")),
            "grey_water_pct": _num(twin.get("grey_water.level_pct")),
            "diesel_pct": _num(twin.get("diesel_tank.level_pct")),
            "heater_on": bool(twin.get("diesel_heater.on")),
            "notices": [
                {"title": n["title"], "message": n["message"], "level": n["level"]}
                for n in notices
            ],
        }

    async def briefing(
        self,
        hub: "Hub",
        notices: list[dict[str, Any]],
        *,
        use_llm: bool,
        persona: str | None = None,
        language: str = "en",
    ) -> str:
        context = self.build_context(hub, notices)
        if use_llm and self.router.active:
            system = build_system(BRIEFING_SYSTEM, language, persona)
            text = await self.router.build_client().chat_text(system, json.dumps(context))
            if text:
                return text.strip()
        return self.render_template(context)

    async def answer(
        self,
        hub: "Hub",
        notices: list[dict[str, Any]],
        question: str,
        *,
        use_llm: bool,
        persona: str | None = None,
        language: str = "en",
        preferences: list[str] | None = None,
    ) -> str:
        """Answer a free-form question from live van state. Read-only: it never
        controls anything — actions go through the intent path (Rule 2)."""
        context = self.build_context(hub, notices)
        if use_llm and self.router.active:
            system = build_system(ANSWER_SYSTEM, language, persona)
            payload = json.dumps(
                {"status": context, "question": question, "preferences": preferences or []}
            )
            text = await self.router.build_client().chat_text(system, payload)
            if text:
                return text.strip()
        # No model could answer (offline, or the configured model failed) — a short
        # localised line, in the assistant's language (never invents data).
        return _ANSWER_FALLBACK.get(language, _ANSWER_FALLBACK["en"])

    async def recommend_camp(
        self,
        hub: "Hub",
        notices: list[dict[str, Any]],
        spots: list[dict[str, Any]],
        wants: list[str],
        *,
        request: str = "",
        use_llm: bool,
        persona: str | None = None,
        language: str = "en",
        preferences: list[str] | None = None,
    ) -> str:
        """Recommend a place to camp from ``spots``, with weather/sun-aware
        micro-siting. Read-only — it proposes, never navigates or acts (Rule 2)."""
        if not spots:
            return _CAMP_NONE.get(language, _CAMP_NONE["en"])
        if use_llm and self.router.active:
            context = self.build_context(hub, notices)
            preds = context.get("predictions") or {}
            current = (self.weather.snapshot().get("current") if self.weather else {}) or {}
            payload = json.dumps(
                {
                    "request": request,
                    "spots": spots,
                    "wants": wants or [],
                    "weather": {
                        "wind_from": current.get("wind_from"),
                        "wind_kmh": current.get("wind_kmh"),
                        "cloud_pct": current.get("cloud_pct"),
                        "condition": current.get("condition"),
                        "rain_eta_hours": self.weather.rain_eta_hours() if self.weather else None,
                    },
                    "sun": {"hour_now": datetime.now().hour, "note": "the sun sets in the west"},
                    # The full resource picture, so the model can weave low battery /
                    # water / grey / diesel into where it sends us.
                    "status": {
                        "battery_soc_pct": context.get("battery_soc_pct"),
                        "battery_days_left": context.get("battery_days_left"),
                        "battery_empty_hours": preds.get("battery_empty_hours"),
                        "fresh_water_pct": context.get("fresh_water_pct"),
                        "fresh_water_empty_hours": preds.get("fresh_water_empty_hours"),
                        "grey_water_pct": context.get("grey_water_pct"),
                        "grey_water_full_hours": preds.get("grey_water_full_hours"),
                        "diesel_pct": context.get("diesel_pct"),
                        "diesel_empty_hours": preds.get("diesel_empty_hours"),
                    },
                    "needs": _camp_needs(context),
                    "notices": context.get("notices", []),
                    "preferences": preferences or [],
                }
            )
            system = build_system(CAMP_SYSTEM, language, persona)
            text = await self.router.build_client().chat_text(system, payload)
            if text:
                return text.strip()
        # Offline: the closest options, and — if a resource is low — surface one that
        # covers it and flag the need (still a plain localised line, invents nothing).
        return self._camp_fallback(hub, notices, spots, language)

    def _camp_fallback(
        self,
        hub: "Hub",
        notices: list[dict[str, Any]],
        spots: list[dict[str, Any]],
        language: str,
    ) -> str:
        lang = language if language in _CAMP_FALLBACK else "en"
        names = ", ".join(f"{s.get('name')} ({s.get('distance_km')} km)" for s in spots[:3])
        line = _CAMP_FALLBACK[lang].format(spots=names)
        # Surface the first low resource that a nearby spot can cover.
        for need in _camp_needs(self.build_context(hub, notices)):
            amenity = need.get("amenity")
            if not amenity:
                continue
            match = next((s for s in spots if amenity in (s.get("amenities") or [])), None)
            if match:
                line += _CAMP_NEED_HINT[lang].format(
                    resource=_NEED_WORD[lang].get(need["resource"], need["resource"]),
                    spot=match.get("name"),
                    amenity=_AMENITY_WORD[lang].get(amenity, amenity),
                )
                break
        return line

    def render_template(self, ctx: dict[str, Any]) -> str:
        parts = [f"{ctx['greeting']}."]
        outside = ctx.get("outside_temp_c")
        cabin = ctx.get("cabin_temp_c")
        if outside is not None and cabin is not None:
            parts.append(f"It's {outside:.0f}°C outside and {cabin:.0f}°C in the cabin.")
        elif outside is not None:
            parts.append(f"It's {outside:.0f}°C outside.")

        days = ctx.get("battery_days_left")
        soc = ctx.get("battery_soc_pct")
        if days is not None:
            parts.append(f"The battery should last about {days:g} more day(s).")
        elif soc is not None:
            parts.append(f"The battery is at {soc:.0f}% and charging.")

        trend = ctx.get("battery_trend_pct_per_hour")
        if trend is not None and trend <= -0.5:
            parts.append(f"It's been dropping about {abs(trend):.1f}% an hour.")

        preds = ctx.get("predictions") or {}
        water_eta = preds.get("fresh_water_empty_hours")
        if water_eta is not None and water_eta < 24:
            parts.append(f"At this rate the fresh water runs out in about {water_eta:g} hours.")

        weather = ctx.get("weather") or {}
        rain_eta = weather.get("rain_eta_hours")
        if rain_eta is not None and rain_eta <= 2:
            when = "shortly" if rain_eta < 0.5 else f"in about {rain_eta:g} hour(s)"
            parts.append(f"Rain is expected {when}.")

        for notice in ctx.get("notices", []):
            parts.append(notice["message"])

        if len(parts) == 1:
            parts.append("Everything looks good — enjoy the journey.")
        return " ".join(parts)


def _camp_needs(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Resources that are running low right now, each tagged with the camp
    `amenity` that would relieve it. Drives both the LLM recommendation and the
    offline fallback so 'we're low on water' shapes where we're sent."""
    preds = ctx.get("predictions") or {}
    needs: list[dict[str, Any]] = []

    fw = ctx.get("fresh_water_pct")
    fw_eta = preds.get("fresh_water_empty_hours")
    if (fw is not None and fw < 25) or (fw_eta is not None and fw_eta < 24):
        needs.append(
            {"resource": "fresh_water", "amenity": "water", "level_pct": fw, "runs_out_in_hours": fw_eta}
        )

    soc = ctx.get("battery_soc_pct")
    days = ctx.get("battery_days_left")
    batt_eta = preds.get("battery_empty_hours")
    if (soc is not None and soc < 30) or (days is not None and days < 1) or (
        batt_eta is not None and batt_eta < 24
    ):
        needs.append(
            {"resource": "battery", "amenity": "power", "level_pct": soc, "days_left": days}
        )

    grey = ctx.get("grey_water_pct")
    grey_eta = preds.get("grey_water_full_hours")
    if (grey is not None and grey > 80) or (grey_eta is not None and grey_eta < 12):
        needs.append(
            {"resource": "grey_water", "amenity": "toilets", "level_pct": grey, "note": "needs dumping"}
        )

    diesel = ctx.get("diesel_pct")
    if diesel is not None and diesel < 20:
        needs.append(
            {"resource": "diesel", "amenity": None, "level_pct": diesel, "note": "refuel en route"}
        )

    return needs


def _local_hour(twin: Any) -> int:
    """Hour of day for the greeting — from the simulated clock (local solar time via
    longitude) when present, else the real wall clock."""
    epoch = _num(twin.get("clock.epoch"))
    if epoch is None:
        return datetime.now().hour
    lon = _num(twin.get("gps.lon")) or 0.0
    utc = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return int((utc.hour + utc.minute / 60.0 + lon / 15.0) % 24)


def _num(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
