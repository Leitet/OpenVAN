"""Simulated camp source — synthetic spots near the van.

Always available (no internet, no key), so every feature can be exercised from the
Hardware Bench and in tests (Rule 1). Deterministic: fixed offsets from the query
point, with descriptions rich enough for the assistant to reason about sun and
wind ("open to the west", "sheltered by pines on the north side").
"""

from __future__ import annotations

from openvan_core import CampSource, CampSpot

# (name, dlat, dlon, kind, amenities, rating, description)
_SPOTS = [
    (
        "Lakeside Meadow",
        0.030,
        0.010,
        "wild",
        ["water", "view"],
        4.6,
        "Quiet grassy spot by a small lake, flat and open to the west — good evening sun.",
    ),
    (
        "Pine Forest Aire",
        -0.020,
        0.020,
        "aire",
        ["water", "toilets", "power"],
        4.1,
        "Gravel aire sheltered by tall pines along the north side; shady in the morning.",
    ),
    (
        "Hilltop Viewpoint",
        0.010,
        -0.030,
        "parking",
        ["view"],
        4.0,
        "Exposed ridge parking with a big sunset view — beautiful but windy, no shelter.",
    ),
    (
        "Riverside Camping",
        -0.030,
        -0.012,
        "campsite",
        ["water", "toilets", "power", "showers"],
        4.4,
        "Small family campsite along the river, tree line on the south side.",
    ),
    (
        "Old Quarry Wild Spot",
        0.015,
        0.026,
        "wild",
        [],
        3.6,
        "Hard-standing in a disused quarry, walls give good shelter from wind on all sides.",
    ),
]


class SimCampSource(CampSource):
    id = "sim"
    name = "Simulated spots"
    requires_internet = False

    async def search(self, lat: float, lon: float, radius_km: float, limit: int = 20):
        spots = [
            CampSpot(
                source="sim",
                source_id=str(i),
                name=name,
                lat=lat + dlat,
                lon=lon + dlon,
                kind=kind,
                amenities=list(amenities),
                rating=rating,
                description=description,
            )
            for i, (name, dlat, dlon, kind, amenities, rating, description) in enumerate(_SPOTS)
        ]
        return spots[:limit]
