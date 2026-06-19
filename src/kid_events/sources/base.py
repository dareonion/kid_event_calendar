"""Common interface every event source adapter implements."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo

from ..models import Event

PACIFIC = ZoneInfo("America/Los_Angeles")


@runtime_checkable
class Source(Protocol):
    """A configured event source.

    ``default_city`` is the fallback city used to geolocate events whose
    location text does not itself name a known city (e.g. single-city library
    systems where the branch string is just a room name).
    """

    key: str
    name: str
    default_city: str
    enabled: bool

    def fetch(self, window_start: datetime, window_end: datetime) -> list[Event]:
        """Return normalized events whose start falls within the window."""
        ...
