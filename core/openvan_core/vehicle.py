"""Vehicle profile — the physical facts about the van.

Accurate decisions need to know the actual vehicle: its **height** (low bridges,
height barriers, ferries), **length + width incl. mirrors** (parking, narrow lanes,
fitting a pitch), **gross weight** (weight-limited roads and bridges), and its
**wheelbase (axelavstånd) + track** (which make the leveling maths exact). The
profile also carries fuel/range, tyres and habitation info, and a Park4Night-style
**category** so places can be matched to the vehicle.

Users pick a **preset** (a real model/variant with standard values) to auto-fill,
then edit anything that differs from their V5C/registration. Values are stored as a
plain dict (persisted in settings) so the set of fields can grow without migrations.

> Preset values are *typical/standard* figures for the base vehicle gathered from
> manufacturer dimension guides — always verify against your own registration
> document, as trims, years and conversions vary.
"""

from __future__ import annotations

from typing import Any

# Park4Night-style vehicle categories (used to match places to the vehicle).
CATEGORIES = [
    {"id": "car", "label": "Car"},
    {"id": "van", "label": "Van / campervan"},
    {"id": "converted_van", "label": "Converted van (fourgon)"},
    {"id": "motorhome", "label": "Motorhome (camping-car)"},
    {"id": "caravan", "label": "Caravan"},
    {"id": "motorbike", "label": "Motorbike"},
    {"id": "bus_truck", "label": "Bus / truck"},
    {"id": "other", "label": "Other"},
]

# The known fields (for the UI to group/render). Not enforced — extra keys are fine.
FIELD_GROUPS: dict[str, list[str]] = {
    "identity": ["make", "model", "variant", "year", "category", "fuel"],
    "dimensions_mm": [
        "length_mm", "width_mm", "width_mirrors_mm", "height_mm",
        "wheelbase_mm", "track_mm", "turning_circle_m", "ground_clearance_mm",
    ],
    "weight_kg": ["kerb_weight_kg", "gross_weight_kg", "payload_kg", "towing_kg"],
    "fuel_range": ["fuel_tank_l", "adblue_l", "consumption_l_100km"],
    "tyres": ["tyre_size", "tyre_pressure_front_bar", "tyre_pressure_rear_bar"],
    "habitation": ["berths", "seats"],
}


def _sevel(make: str, model: str, variant: str, **kw: Any) -> dict[str, Any]:
    """Fiat Ducato / Citroën Jumper / Peugeot Boxer / (Opel Movano 2021+) share the
    Sevel platform, so common values live here and the L/H variant overrides size."""
    base = {
        "make": make, "model": model, "variant": variant,
        "category": "converted_van", "fuel": "diesel",
        "width_mm": 2050, "width_mirrors_mm": 2520, "track_mm": 1810,
        "gross_weight_kg": 3500, "towing_kg": 2500,
        "fuel_tank_l": 90, "adblue_l": 19, "consumption_l_100km": 8.5,
        "tyre_size": "225/75 R16C",
    }
    base.update(kw)
    return base


# Real models with standard values — a starting library; the set is easy to extend.
PRESETS: dict[str, dict[str, Any]] = {
    # --- Sevel platform (Ducato / Jumper / Boxer / ProMaster) ---
    "citroen_jumper_l2h2": _sevel("Citroën", "Jumper", "L2H2",
        length_mm=5413, height_mm=2524, wheelbase_mm=3450, turning_circle_m=12.0, kerb_weight_kg=2080),
    "citroen_jumper_l3h2": _sevel("Citroën", "Jumper", "L3H2",
        length_mm=5998, height_mm=2524, wheelbase_mm=4035, turning_circle_m=13.4, kerb_weight_kg=2160),
    "citroen_jumper_l4h3": _sevel("Citroën", "Jumper", "L4H3",
        length_mm=6363, height_mm=2764, wheelbase_mm=4035, turning_circle_m=14.2, kerb_weight_kg=2250),
    "fiat_ducato_l2h2": _sevel("Fiat", "Ducato", "L2H2",
        length_mm=5413, height_mm=2524, wheelbase_mm=3450, turning_circle_m=12.0, kerb_weight_kg=2080),
    "fiat_ducato_l4h3": _sevel("Fiat", "Ducato", "L4H3 Maxi",
        length_mm=6363, height_mm=2764, wheelbase_mm=4035, turning_circle_m=14.2,
        kerb_weight_kg=2300, gross_weight_kg=4005),
    "peugeot_boxer_l3h2": _sevel("Peugeot", "Boxer", "L3H2",
        length_mm=5998, height_mm=2524, wheelbase_mm=4035, turning_circle_m=13.4, kerb_weight_kg=2160),
    "ram_promaster_2500_159": _sevel("RAM", "ProMaster 2500", "159\" High Roof",
        length_mm=5817, width_mirrors_mm=2489, height_mm=2669, wheelbase_mm=3785,
        turning_circle_m=11.9, kerb_weight_kg=2350, gross_weight_kg=4010,
        consumption_l_100km=11.0, adblue_l=None),
    # --- Mercedes Sprinter (VS30) ---
    "mercedes_sprinter_l2h2": {
        "make": "Mercedes-Benz", "model": "Sprinter", "variant": "L2H2 (MWB)",
        "category": "converted_van", "fuel": "diesel",
        "length_mm": 5932, "width_mm": 2020, "width_mirrors_mm": 2345, "height_mm": 2585,
        "wheelbase_mm": 3924, "track_mm": 1720, "turning_circle_m": 13.4,
        "kerb_weight_kg": 2225, "gross_weight_kg": 3500, "towing_kg": 2000,
        "fuel_tank_l": 71, "adblue_l": 22, "consumption_l_100km": 9.0, "tyre_size": "235/65 R16C",
    },
    "mercedes_sprinter_l3h2": {
        "make": "Mercedes-Benz", "model": "Sprinter", "variant": "L3H2 (LWB)",
        "category": "converted_van", "fuel": "diesel",
        "length_mm": 6967, "width_mm": 2020, "width_mirrors_mm": 2345, "height_mm": 2585,
        "wheelbase_mm": 4325, "track_mm": 1720, "turning_circle_m": 15.6,
        "kerb_weight_kg": 2400, "gross_weight_kg": 3500, "towing_kg": 2000,
        "fuel_tank_l": 71, "adblue_l": 22, "consumption_l_100km": 9.5, "tyre_size": "235/65 R16C",
    },
    # --- Ford Transit (2014+) ---
    "ford_transit_l3h2": {
        "make": "Ford", "model": "Transit", "variant": "L3H2",
        "category": "converted_van", "fuel": "diesel",
        "length_mm": 5981, "width_mm": 2059, "width_mirrors_mm": 2474, "height_mm": 2549,
        "wheelbase_mm": 3750, "track_mm": 1710, "turning_circle_m": 13.1,
        "kerb_weight_kg": 2100, "gross_weight_kg": 3500, "towing_kg": 2800,
        "fuel_tank_l": 80, "adblue_l": 21, "consumption_l_100km": 9.0, "tyre_size": "235/65 R16C",
    },
    "ford_transit_l4h3": {
        "make": "Ford", "model": "Transit", "variant": "L4H3 (Jumbo)",
        "category": "converted_van", "fuel": "diesel",
        "length_mm": 6704, "width_mm": 2059, "width_mirrors_mm": 2474, "height_mm": 2782,
        "wheelbase_mm": 3954, "track_mm": 1710, "turning_circle_m": 14.4,
        "kerb_weight_kg": 2250, "gross_weight_kg": 3500, "towing_kg": 2500,
        "fuel_tank_l": 80, "adblue_l": 21, "consumption_l_100km": 9.5, "tyre_size": "235/65 R16C",
    },
    # --- VW Crafter / MAN TGE (shared) ---
    "vw_crafter_l4h3": {
        "make": "Volkswagen", "model": "Crafter", "variant": "L4H3",
        "category": "converted_van", "fuel": "diesel",
        "length_mm": 6836, "width_mm": 2040, "width_mirrors_mm": 2427, "height_mm": 2798,
        "wheelbase_mm": 4490, "track_mm": 1720, "turning_circle_m": 16.0,
        "kerb_weight_kg": 2400, "gross_weight_kg": 3500, "towing_kg": 2500,
        "fuel_tank_l": 75, "adblue_l": 18, "consumption_l_100km": 9.5, "tyre_size": "235/65 R16C",
    },
    "man_tge_l3h3": {
        "make": "MAN", "model": "TGE", "variant": "L3H3",
        "category": "converted_van", "fuel": "diesel",
        "length_mm": 5986, "width_mm": 2040, "width_mirrors_mm": 2427, "height_mm": 2590,
        "wheelbase_mm": 3640, "track_mm": 1720, "turning_circle_m": 13.6,
        "kerb_weight_kg": 2350, "gross_weight_kg": 3500, "towing_kg": 2500,
        "fuel_tank_l": 75, "adblue_l": 18, "consumption_l_100km": 9.3, "tyre_size": "235/65 R16C",
    },
    # --- Renault Master / Opel Movano / Nissan Interstar ---
    "renault_master_l2h2": {
        "make": "Renault", "model": "Master", "variant": "L2H2",
        "category": "converted_van", "fuel": "diesel",
        "length_mm": 5548, "width_mm": 2070, "width_mirrors_mm": 2470, "height_mm": 2499,
        "wheelbase_mm": 3682, "track_mm": 1730, "turning_circle_m": 13.6,
        "kerb_weight_kg": 2080, "gross_weight_kg": 3500, "towing_kg": 2500,
        "fuel_tank_l": 100, "adblue_l": 22, "consumption_l_100km": 9.5, "tyre_size": "225/65 R16C",
    },
    # --- Smaller campervans (van category) ---
    "vw_california_t61": {
        "make": "Volkswagen", "model": "California", "variant": "T6.1 Ocean",
        "category": "van", "fuel": "diesel",
        "length_mm": 4904, "width_mm": 1904, "width_mirrors_mm": 2297, "height_mm": 1990,
        "wheelbase_mm": 3000, "track_mm": 1628, "turning_circle_m": 11.9,
        "kerb_weight_kg": 2200, "gross_weight_kg": 3080, "towing_kg": 2000,
        "fuel_tank_l": 70, "adblue_l": 13, "consumption_l_100km": 8.0, "tyre_size": "215/60 R17",
        "berths": 4, "seats": 4,
    },
    "ford_transit_custom_nugget": {
        "make": "Ford", "model": "Transit Custom", "variant": "Nugget",
        "category": "van", "fuel": "diesel",
        "length_mm": 5340, "width_mm": 1986, "width_mirrors_mm": 2272, "height_mm": 1986,
        "wheelbase_mm": 3300, "track_mm": 1710, "turning_circle_m": 12.4,
        "kerb_weight_kg": 2100, "gross_weight_kg": 3000, "towing_kg": 2000,
        "fuel_tank_l": 70, "adblue_l": 21, "consumption_l_100km": 8.5, "tyre_size": "215/65 R16C",
        "berths": 4, "seats": 4,
    },
    "renault_trafic_l2h1": {
        "make": "Renault", "model": "Trafic", "variant": "L2H1",
        "category": "van", "fuel": "diesel",
        "length_mm": 5399, "width_mm": 1956, "width_mirrors_mm": 2283, "height_mm": 1971,
        "wheelbase_mm": 3498, "track_mm": 1660, "turning_circle_m": 13.2,
        "kerb_weight_kg": 1900, "gross_weight_kg": 3070, "towing_kg": 2000,
        "fuel_tank_l": 80, "adblue_l": 20, "consumption_l_100km": 8.0, "tyre_size": "205/65 R16C",
    },
    "peugeot_expert_proace_l": {
        "make": "Peugeot / Toyota", "model": "Expert / Proace", "variant": "L (Long)",
        "category": "van", "fuel": "diesel",
        "length_mm": 5309, "width_mm": 1920, "width_mirrors_mm": 2204, "height_mm": 1935,
        "wheelbase_mm": 3275, "track_mm": 1630, "turning_circle_m": 12.9,
        "kerb_weight_kg": 1720, "gross_weight_kg": 3100, "towing_kg": 2000,
        "fuel_tank_l": 69, "adblue_l": 17, "consumption_l_100km": 7.5, "tyre_size": "215/60 R17",
    },
    # --- Larger / coachbuilt base ---
    "iveco_daily_35s_l4h3": {
        "make": "Iveco", "model": "Daily", "variant": "35S L4H3",
        "category": "converted_van", "fuel": "diesel",
        "length_mm": 7170, "width_mm": 2065, "width_mirrors_mm": 2340, "height_mm": 2760,
        "wheelbase_mm": 4100, "track_mm": 1740, "turning_circle_m": 13.4,
        "kerb_weight_kg": 2500, "gross_weight_kg": 3500, "towing_kg": 3500,
        "fuel_tank_l": 100, "adblue_l": 20, "consumption_l_100km": 10.5, "tyre_size": "225/65 R16C",
    },
    "iveco_daily_35s_l2h2": {
        "make": "Iveco", "model": "Daily", "variant": "35S L2H2",
        "category": "converted_van", "fuel": "diesel",
        "length_mm": 5480, "width_mm": 2065, "width_mirrors_mm": 2340, "height_mm": 2280,
        "wheelbase_mm": 3520, "track_mm": 1740, "turning_circle_m": 12.4,
        "kerb_weight_kg": 2200, "gross_weight_kg": 3500, "towing_kg": 3500,
        "fuel_tank_l": 70, "adblue_l": 20, "consumption_l_100km": 9.5, "tyre_size": "195/75 R16C",
    },
    # --- More Sevel variants ---
    "fiat_ducato_l3h2": _sevel("Fiat", "Ducato", "L3H2",
        length_mm=5998, height_mm=2524, wheelbase_mm=4035, turning_circle_m=13.4, kerb_weight_kg=2160),
    "peugeot_boxer_l4h2": _sevel("Peugeot", "Boxer", "L4H2",
        length_mm=6363, height_mm=2524, wheelbase_mm=4035, turning_circle_m=14.2, kerb_weight_kg=2250),
    "ram_promaster_1500_136": _sevel("RAM", "ProMaster 1500", "136\" High Roof",
        length_mm=5232, width_mirrors_mm=2489, height_mm=2522, wheelbase_mm=3454,
        turning_circle_m=11.1, kerb_weight_kg=2200, consumption_l_100km=11.0, adblue_l=None),
    # --- More Sprinter (long + 4x4) ---
    "mercedes_sprinter_l4h2": {
        "make": "Mercedes-Benz", "model": "Sprinter", "variant": "L4H2 (extra-long)",
        "category": "converted_van", "fuel": "diesel",
        "length_mm": 7367, "width_mm": 2020, "width_mirrors_mm": 2345, "height_mm": 2585,
        "wheelbase_mm": 4325, "track_mm": 1720, "turning_circle_m": 16.5,
        "kerb_weight_kg": 2500, "gross_weight_kg": 5000, "towing_kg": 2000,
        "fuel_tank_l": 93, "adblue_l": 22, "consumption_l_100km": 9.8, "tyre_size": "235/65 R16C",
    },
    "mercedes_sprinter_4x4_l3h2": {
        "make": "Mercedes-Benz", "model": "Sprinter 4x4", "variant": "L3H2",
        "category": "converted_van", "fuel": "diesel",
        "length_mm": 6967, "width_mm": 2020, "width_mirrors_mm": 2345, "height_mm": 2620,
        "wheelbase_mm": 4325, "track_mm": 1730, "turning_circle_m": 15.6,
        "ground_clearance_mm": 210, "kerb_weight_kg": 2550, "gross_weight_kg": 3880,
        "towing_kg": 2000, "fuel_tank_l": 71, "adblue_l": 22, "consumption_l_100km": 10.5,
        "tyre_size": "265/70 R16",
    },
    # --- Coachbuilt / finished motorhomes (motorhome category) ---
    "vw_grand_california_600": {
        "make": "Volkswagen", "model": "Grand California", "variant": "600",
        "category": "motorhome", "fuel": "diesel",
        "length_mm": 5986, "width_mm": 2040, "width_mirrors_mm": 2427, "height_mm": 2960,
        "wheelbase_mm": 3640, "track_mm": 1720, "turning_circle_m": 13.6,
        "kerb_weight_kg": 3000, "gross_weight_kg": 3880, "towing_kg": 2000,
        "fuel_tank_l": 75, "adblue_l": 18, "consumption_l_100km": 10.0, "tyre_size": "235/65 R16C",
        "berths": 4, "seats": 4,
    },
    "vw_grand_california_680": {
        "make": "Volkswagen", "model": "Grand California", "variant": "680",
        "category": "motorhome", "fuel": "diesel",
        "length_mm": 6836, "width_mm": 2040, "width_mirrors_mm": 2427, "height_mm": 2960,
        "wheelbase_mm": 4490, "track_mm": 1720, "turning_circle_m": 16.0,
        "kerb_weight_kg": 3100, "gross_weight_kg": 4000, "towing_kg": 2000,
        "fuel_tank_l": 75, "adblue_l": 18, "consumption_l_100km": 10.5, "tyre_size": "235/65 R16C",
        "berths": 4, "seats": 4,
    },
    "coachbuilt_ducato_typical": {
        "make": "Coachbuilt", "model": "on Fiat Ducato", "variant": "typical (overcab)",
        "category": "motorhome", "fuel": "diesel",
        "length_mm": 7000, "width_mm": 2300, "width_mirrors_mm": 2500, "height_mm": 2900,
        "wheelbase_mm": 4035, "track_mm": 1810, "turning_circle_m": 14.5,
        "kerb_weight_kg": 3000, "gross_weight_kg": 3500, "towing_kg": 2000,
        "fuel_tank_l": 90, "adblue_l": 19, "consumption_l_100km": 11.0, "tyre_size": "225/75 R16CP",
        "berths": 4, "seats": 4,
    },
    # --- Pop-top / MPV campers (van category) ---
    "mercedes_marco_polo": {
        "make": "Mercedes-Benz", "model": "V-Class Marco Polo", "variant": "",
        "category": "van", "fuel": "diesel",
        "length_mm": 5140, "width_mm": 1928, "width_mirrors_mm": 2249, "height_mm": 1910,
        "wheelbase_mm": 3430, "track_mm": 1650, "turning_circle_m": 11.8,
        "kerb_weight_kg": 2200, "gross_weight_kg": 3200, "towing_kg": 2000,
        "fuel_tank_l": 70, "adblue_l": 22, "consumption_l_100km": 7.5, "tyre_size": "225/55 R17",
        "berths": 4, "seats": 4,
    },
    "ford_transit_custom_l2h1": {
        "make": "Ford", "model": "Transit Custom", "variant": "L2H1",
        "category": "van", "fuel": "diesel",
        "length_mm": 5339, "width_mm": 1986, "width_mirrors_mm": 2272, "height_mm": 1986,
        "wheelbase_mm": 3300, "track_mm": 1710, "turning_circle_m": 12.4,
        "kerb_weight_kg": 2000, "gross_weight_kg": 3200, "towing_kg": 2000,
        "fuel_tank_l": 70, "adblue_l": 21, "consumption_l_100km": 8.0, "tyre_size": "215/65 R16C",
    },
    "toyota_hiace_lwb": {
        "make": "Toyota", "model": "HiAce", "variant": "LWB",
        "category": "van", "fuel": "diesel",
        "length_mm": 5265, "width_mm": 1950, "width_mirrors_mm": 2235, "height_mm": 1990,
        "wheelbase_mm": 3210, "track_mm": 1655, "turning_circle_m": 11.0,
        "kerb_weight_kg": 2000, "gross_weight_kg": 3000, "towing_kg": 1500,
        "fuel_tank_l": 70, "consumption_l_100km": 8.5, "tyre_size": "195/80 R15",
    },
    # --- Electric ---
    "renault_master_etech_l2h2": {
        "make": "Renault", "model": "Master E-Tech", "variant": "L2H2 (electric)",
        "category": "converted_van", "fuel": "electric",
        "length_mm": 5548, "width_mm": 2070, "width_mirrors_mm": 2470, "height_mm": 2499,
        "wheelbase_mm": 3682, "track_mm": 1730, "turning_circle_m": 13.6,
        "kerb_weight_kg": 2300, "gross_weight_kg": 3500, "towing_kg": 0,
        "tyre_size": "225/65 R16C",
    },
    "vw_id_buzz": {
        "make": "Volkswagen", "model": "ID. Buzz", "variant": "(electric)",
        "category": "van", "fuel": "electric",
        "length_mm": 4712, "width_mm": 1985, "width_mirrors_mm": 2212, "height_mm": 1937,
        "wheelbase_mm": 2988, "track_mm": 1700, "turning_circle_m": 11.1,
        "kerb_weight_kg": 2400, "gross_weight_kg": 3000, "towing_kg": 1000,
        "tyre_size": "235/55 R18", "seats": 5,
    },
}


def presets_list() -> list[dict[str, Any]]:
    """Presets for the UI picker — id + display name + the full spec."""
    out = []
    for pid, spec in PRESETS.items():
        name = " ".join(x for x in (spec.get("make"), spec.get("model"), spec.get("variant")) if x)
        out.append({"id": pid, "name": name, "spec": spec})
    return out


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def vehicle_summary(vehicle: dict[str, Any] | None) -> dict[str, Any] | None:
    """A compact, decision-relevant view for the assistant (metres/tonnes), so it
    can warn about low bridges, weight limits and tight spots. None if unset."""
    if not vehicle:
        return None
    out: dict[str, Any] = {}
    name = " ".join(
        str(x) for x in (vehicle.get("make"), vehicle.get("model"), vehicle.get("variant")) if x
    )
    if name:
        out["name"] = name
    if vehicle.get("category"):
        out["category"] = vehicle["category"]
    for key, mm in (("height_m", "height_mm"), ("length_m", "length_mm"),
                    ("width_m", "width_mm"), ("width_mirrors_m", "width_mirrors_mm")):
        val = _num(vehicle.get(mm))
        if val is not None:
            out[key] = round(val / 1000, 2)
    for key in ("gross_weight_kg", "kerb_weight_kg", "fuel_tank_l"):
        if _num(vehicle.get(key)) is not None:
            out[key] = _num(vehicle[key])
    return out or None
