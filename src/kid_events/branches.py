"""Resolve an event's branch/location text to coordinates via city centroids.

Library branches are spread across a small, fixed set of cities. For a 5-20 mile
radius decision, the centroid of the branch's city is well within tolerance of
the exact branch address, and far more robust than hand-geocoding every branch.
The lookup detects a known city name inside the branch/location string and falls
back to the source library's default city.
"""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files

from pydantic import BaseModel, Field


class Coord(BaseModel):
    lat: float
    lon: float


class LocationBook(BaseModel):
    center_name: str
    center: Coord
    cities: dict[str, Coord]
    # Optional per-branch coordinates, keyed by source_key then lowercased branch
    # label, for sources that don't expose real coordinates (e.g. Mississauga).
    branches: dict[str, dict[str, Coord]] = Field(default_factory=dict)

    def branch_coord(self, source_key: str, label: str) -> Coord | None:
        """Exact per-branch coordinate for a source's branch label, if known."""
        return self.branches.get(source_key, {}).get(label.strip().lower())

    def resolve(
        self, location_name: str | None, default_city: str = ""
    ) -> tuple[float | None, float | None, str]:
        """Return ``(lat, lon, city_label)`` for a branch/location string.

        Online/virtual events resolve to no coordinates. Otherwise the first
        known city name found in the text wins (longer names first, so
        "Los Altos Hills" beats "Los Altos"); failing that, the source's
        ``default_city`` is used.
        """
        text = (location_name or "").lower()
        if "online" in text or "virtual" in text:
            return None, None, "Online"
        for city in sorted(self.cities, key=len, reverse=True):
            if city in text:
                coord = self.cities[city]
                return coord.lat, coord.lon, city.title()
        default = default_city.lower().strip()
        if default in self.cities:
            coord = self.cities[default]
            return coord.lat, coord.lon, default.title()
        return None, None, default_city.title()


@lru_cache
def load_location_book() -> LocationBook:
    raw = files("kid_events").joinpath("data/branches.json").read_text(encoding="utf-8")
    return LocationBook.model_validate_json(raw)
