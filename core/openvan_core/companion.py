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
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .llm import LLMClient

if TYPE_CHECKING:  # pragma: no cover
    from .hub import Hub

BRIEFING_SYSTEM = """\
You are OpenVan, a warm and concise travel companion living in a camper van.
Given the current status as JSON, write a short, friendly spoken briefing of
2-4 sentences. Greet by time of day. Mention only what is relevant or
noteworthy (especially anything in `notices`). Never invent data beyond what is
given. Plain natural speech — no lists, no markdown, no headings.
"""

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
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def build_context(
        self, hub: "Hub", notices: list[dict[str, Any]], *, hour: int | None = None
    ) -> dict[str, Any]:
        twin = hub.twin
        hour = datetime.now().hour if hour is None else hour

        soc = _num(twin.get("house_battery.soc"))
        current = _num(twin.get("house_battery.current"))
        battery_days = None
        if soc is not None and current is not None and current < -0.05:
            battery_days = round(
                _BATTERY_CAPACITY_AH * (soc / 100.0) / abs(current) / 24.0, 1
            )

        return {
            "hour": hour,
            "greeting": _greeting(hour),
            "outside_temp_c": _num(twin.get("outside.temperature")),
            "cabin_temp_c": _num(twin.get("cabin.temperature")),
            "battery_soc_pct": soc,
            "battery_days_left": battery_days,
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
        self, hub: "Hub", notices: list[dict[str, Any]], *, use_llm: bool
    ) -> str:
        context = self.build_context(hub, notices)
        if use_llm:
            text = await self.client.chat_text(BRIEFING_SYSTEM, json.dumps(context))
            if text:
                return text.strip()
        return self.render_template(context)

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

        for notice in ctx.get("notices", []):
            parts.append(notice["message"])

        if len(parts) == 1:
            parts.append("Everything looks good — enjoy the journey.")
        return " ".join(parts)


def _num(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
