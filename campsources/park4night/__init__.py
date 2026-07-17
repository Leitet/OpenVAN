"""Park4Night camp source — the pattern for a proprietary, keyed provider.

Park4Night / iOverlander have no official public API, so this is the *template* for
adding a source that needs credentials. It drops in exactly like the keyless OSM
source; you supply access via the environment:

    OPENVAN_PARK4NIGHT_KEY=…      # your API key / token
    OPENVAN_PARK4NIGHT_URL=…      # their API or your own proxy endpoint

Without a key it is simply unavailable (the service skips it), just as the OSM
source is when offline. The endpoint is expected to accept ``lat``, ``lon``,
``radius_km`` and return JSON ``{"places": [{id, name, lat, lon|lng, type,
services:[…], note, url}]}`` — adjust ``_parse`` to match the real response.
"""

from __future__ import annotations

import os

import httpx

from openvan_core import CampSource, CampSpot

_KIND = {"camping": "campsite", "aire": "aire", "wild": "wild", "parking": "parking"}


class Park4NightSource(CampSource):
    id = "park4night"
    name = "Park4Night"
    requires_internet = True
    requires_key = True

    @staticmethod
    def _key() -> str | None:
        return os.environ.get("OPENVAN_PARK4NIGHT_KEY")

    @staticmethod
    def _url() -> str | None:
        return os.environ.get("OPENVAN_PARK4NIGHT_URL")

    async def available(self) -> bool:
        return bool(self._key() and self._url())

    async def search(self, lat: float, lon: float, radius_km: float, limit: int = 20):
        key, url = self._key(), self._url()
        if not (key and url):
            return []
        params = {"lat": lat, "lon": lon, "radius_km": radius_km, "limit": limit}
        headers = {
            "Authorization": f"Bearer {key}",
            "User-Agent": "OpenVan/0.1 (camper-van assistant)",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return self._parse(data, limit)

    @staticmethod
    def _parse(data, limit: int) -> list[CampSpot]:
        places = data.get("places", []) if isinstance(data, dict) else (data or [])
        spots: list[CampSpot] = []
        for p in places[:limit]:
            plat = p.get("lat")
            plon = p.get("lon", p.get("lng"))
            if plat is None or plon is None:
                continue
            spots.append(
                CampSpot(
                    source="park4night",
                    source_id=str(p.get("id")),
                    name=p.get("name") or "Park4Night spot",
                    lat=float(plat),
                    lon=float(plon),
                    kind=_KIND.get(p.get("type"), "unknown"),
                    amenities=list(p.get("services") or []),
                    rating=p.get("rating"),
                    description=p.get("note") or p.get("description"),
                    url=p.get("url") or p.get("link"),
                )
            )
        return spots
