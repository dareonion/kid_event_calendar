"""Straight-line distance helpers and the driving-radius presets."""

from __future__ import annotations

import math

EARTH_RADIUS_MI = 3958.7613


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in miles."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(a))


# key -> (label, max miles). ``None`` miles means "no distance limit".
RADIUS_PRESETS: dict[str, tuple[str, float | None]] = {
    "mv": ("Mountain View only (~5 mi)", 5.0),
    "near": ("~15 min drive (~10 mi)", 10.0),
    "far": ("~30 min drive (~20 mi)", 20.0),
    "any": ("Any distance", None),
}
DEFAULT_RADIUS = "far"


def radius_miles(key: str) -> float | None:
    """Miles for a preset key, or ``None`` for unlimited / unknown keys."""
    preset = RADIUS_PRESETS.get(key)
    return preset[1] if preset else None
