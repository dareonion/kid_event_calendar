"""Canonical data model shared across sources, filters, and the web UI."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class AgeBand(StrEnum):
    """A normalized audience age band that every source is mapped onto.

    The ``(min_months, max_months)`` ranges are inclusive and non-overlapping for
    the child-specific bands; ``ALL_AGES`` deliberately spans everything so that
    family / all-ages events match any child's age.
    """

    INFANT = "infant"
    TODDLER = "toddler"
    PRESCHOOL = "preschool"
    SCHOOL_AGE = "school_age"
    TWEEN_TEEN = "tween_teen"
    ADULT = "adult"
    ALL_AGES = "all_ages"

    @property
    def label(self) -> str:
        return _BAND_META[self][0]

    @property
    def min_months(self) -> int:
        return _BAND_META[self][1]

    @property
    def max_months(self) -> int:
        return _BAND_META[self][2]

    @property
    def is_kid(self) -> bool:
        """Whether this band describes children (excludes ADULT)."""
        return self not in (AgeBand.ADULT,)


# label, min_months (inclusive), max_months (inclusive)
_BAND_META: dict[AgeBand, tuple[str, int, int]] = {
    AgeBand.INFANT: ("Infant (0-18 mo)", 0, 17),
    AgeBand.TODDLER: ("Toddler (18-36 mo)", 18, 35),
    AgeBand.PRESCHOOL: ("Preschool (3-5 yr)", 36, 71),
    AgeBand.SCHOOL_AGE: ("School age (6-11 yr)", 72, 143),
    AgeBand.TWEEN_TEEN: ("Tween / Teen (12-18 yr)", 144, 216),
    AgeBand.ADULT: ("Adult (18+)", 216, 1200),
    AgeBand.ALL_AGES: ("All ages / Family", 0, 1200),
}

# Display order used by the UI (youngest kid bands first, ALL_AGES last).
BAND_ORDER: list[AgeBand] = [
    AgeBand.INFANT,
    AgeBand.TODDLER,
    AgeBand.PRESCHOOL,
    AgeBand.SCHOOL_AGE,
    AgeBand.TWEEN_TEEN,
    AgeBand.ADULT,
    AgeBand.ALL_AGES,
]


class Event(BaseModel):
    """A single normalized, kid-relevant event from one source."""

    id: str
    source: str
    source_key: str
    title: str
    description: str = ""
    url: str | None = None
    start: datetime
    end: datetime | None = None
    location_name: str = ""
    city: str = ""
    lat: float | None = None
    lon: float | None = None
    distance_mi: float | None = None
    age_bands: list[AgeBand] = Field(default_factory=list)
    age_inferred: bool = False
    registration_required: bool = False
    is_cancelled: bool = False

    @property
    def age_band_labels(self) -> list[str]:
        return [band.label for band in self.age_bands]

    def has_known_location(self) -> bool:
        return self.lat is not None and self.lon is not None
