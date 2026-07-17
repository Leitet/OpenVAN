"""Simulated camp source — synthetic spots near the van.

Always available (no internet, no key), so every feature can be exercised from the
Hardware Bench and in tests (Rule 1). Descriptions are rich enough for the
assistant to reason about sun and wind ("open to the west", "sheltered by pines on
the north side").

Real camp spots (Overpass, Park4Night) sit at fixed world coordinates. To behave
the same way — so they stay put on the map while you drive rather than sliding
along with the van — these synthetic spots are anchored to a coarse **grid cell**
(``_GRID``°) around the query point, not to the live GPS. Within a cell the spots
are stationary; crossing into a new region reveals a fresh set.
"""

from __future__ import annotations

from openvan_core import CampSource, CampSpot

# Anchor spots to a ~0.1° (~11 km) grid so they're stationary while driving.
_GRID = 0.1

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
        # Snap to the grid cell so the same spots come back at the same coordinates
        # as the van moves within a region — stationary on the map, like real POIs.
        base_lat = round(lat / _GRID) * _GRID
        base_lon = round(lon / _GRID) * _GRID
        spots = [
            CampSpot(
                source="sim",
                source_id=str(i),
                name=name,
                lat=round(base_lat + dlat, 6),
                lon=round(base_lon + dlon, 6),
                kind=kind,
                amenities=list(amenities),
                rating=rating,
                description=description,
            )
            for i, (name, dlat, dlon, kind, amenities, rating, description) in enumerate(_SPOTS)
        ]
        return spots[:limit]
