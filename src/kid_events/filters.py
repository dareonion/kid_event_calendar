"""Pure, in-memory filtering and sorting of the cached event list."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .ages import child_age_to_bands
from .models import AgeBand, Event


class SortKey(StrEnum):
    DATE = "date"
    DISTANCE = "distance"


class FilterParams(BaseModel):
    # If child_age_months is set it takes precedence over age_bands; if both are
    # empty there is no age filter (all ages shown).
    child_age_months: int | None = None
    age_bands: set[AgeBand] = Field(default_factory=set)
    max_miles: float | None = None
    include_unknown_location: bool = True
    date_from: datetime | None = None
    date_to: datetime | None = None
    keyword: str = ""
    sources: set[str] = Field(default_factory=set)
    sort: SortKey = SortKey.DATE

    def desired_bands(self) -> set[AgeBand] | None:
        """Bands an event must overlap, or ``None`` for no age filter."""
        if self.child_age_months is not None:
            return child_age_to_bands(self.child_age_months)
        if self.age_bands:
            return set(self.age_bands)
        return None


def _matches(event: Event, params: FilterParams, desired: set[AgeBand] | None) -> bool:
    if desired is not None and not (set(event.age_bands) & desired):
        return False

    if params.max_miles is not None:
        if event.distance_mi is None:
            if not params.include_unknown_location:
                return False
        elif event.distance_mi > params.max_miles:
            return False

    if params.date_from is not None and event.start < params.date_from:
        return False
    if params.date_to is not None and event.start > params.date_to:
        return False

    if params.sources and event.source_key not in params.sources:
        return False

    if params.keyword:
        haystack = f"{event.title}\n{event.description}".lower()
        if params.keyword.lower() not in haystack:
            return False

    return True


def _sort_key(sort: SortKey) -> Callable[[Event], Any]:
    if sort is SortKey.DISTANCE:
        # Unknown-distance events sort last, then by start time.
        return lambda event: (event.distance_mi is None, event.distance_mi or 0.0, event.start)
    return lambda event: event.start


def apply_filters(events: list[Event], params: FilterParams) -> list[Event]:
    desired = params.desired_bands()
    matched = [event for event in events if _matches(event, params, desired)]
    matched.sort(key=_sort_key(params.sort))
    return matched
