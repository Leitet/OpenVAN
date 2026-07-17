"""OpenStreetMap camp source via the Overpass API.

Real camp/aire data, **keyless and free** — the same offline-first, no-API-key
ethos as the open-meteo weather source. Park4Night / iOverlander are proprietary;
OSM is the open reference. Needs internet; fails gracefully (returns []) when
offline, and the service serves its cache instead.

A user adds another site (a proprietary one, a self-hosted proxy, …) by dropping a
sibling package here that subclasses CampSource — exactly like adding a plugin.
"""

from __future__ import annotations

import httpx

from openvan_core import CampSource, CampSpot

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Overpass (like Nominatim) requires a descriptive User-Agent per its usage policy;
# without one it replies 406.
_HEADERS = {"User-Agent": "OpenVan/0.1 (camper-van assistant)", "Accept": "application/json"}
_KIND = {"camp_site": "campsite", "caravan_site": "aire"}


def _amenities(tags: dict) -> list[str]:
    out = []
    if tags.get("drinking_water") in ("yes", "1") or tags.get("water") == "yes":
        out.append("water")
    if tags.get("toilets") in ("yes", "1"):
        out.append("toilets")
    if tags.get("power_supply") in ("yes", "1"):
        out.append("power")
    if tags.get("shower") in ("yes", "1"):
        out.append("showers")
    return out


class OverpassCampSource(CampSource):
    id = "overpass"
    name = "OpenStreetMap (Overpass)"
    requires_internet = True

    async def search(self, lat: float, lon: float, radius_km: float, limit: int = 20):
        radius_m = int(radius_km * 1000)
        query = (
            f"[out:json][timeout:15];("
            f'node["tourism"~"camp_site|caravan_site"](around:{radius_m},{lat},{lon});'
            f'way["tourism"~"camp_site|caravan_site"](around:{radius_m},{lat},{lon});'
            f");out center {limit};"
        )
        async with httpx.AsyncClient(timeout=httpx.Timeout(18.0, connect=5.0)) as client:
            resp = await client.post(_OVERPASS_URL, data={"data": query}, headers=_HEADERS)
            resp.raise_for_status()
            data = resp.json()

        spots: list[CampSpot] = []
        for el in data.get("elements", []):
            tags = el.get("tags", {}) or {}
            plat = el.get("lat") or (el.get("center") or {}).get("lat")
            plon = el.get("lon") or (el.get("center") or {}).get("lon")
            if plat is None or plon is None:
                continue
            spots.append(
                CampSpot(
                    source="overpass",
                    source_id=str(el.get("id")),
                    name=tags.get("name") or "Unnamed camp",
                    lat=float(plat),
                    lon=float(plon),
                    kind=_KIND.get(tags.get("tourism"), "campsite"),
                    amenities=_amenities(tags),
                    url=tags.get("website") or tags.get("contact:website"),
                )
            )
        return spots
