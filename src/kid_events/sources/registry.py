"""The configured set of event sources.

Adding a library later is a one-line entry here that reuses an existing adapter.
"""

from __future__ import annotations

from .base import Source
from .bibliocommons import BiblioCommonsSource
from .libcal import LibCalSource

ALL_SOURCES: list[Source] = [
    BiblioCommonsSource("paloalto", "Palo Alto City Library", "paloalto", "palo alto"),
    BiblioCommonsSource("sccl", "Santa Clara County Library", "sccl", ""),
    BiblioCommonsSource("sjpl", "San Jose Public Library", "sjpl", "san jose"),
    LibCalSource(
        "mountainview",
        "Mountain View Public Library",
        "https://mountainview.libcal.com/ical_subscribe.php?cid=8800",
        "mountain view",
    ),
    # Sunnyvale uses LibCal too, but its ical_subscribe rejects the public
    # calendar id (cid=13025 -> "invalid calendar id"). Re-enable once the real
    # iCal feed id is captured from the calendar's "Subscribe / iCal" link.
    LibCalSource(
        "sunnyvale",
        "Sunnyvale Public Library",
        "https://sunnyvale.libcal.com/ical_subscribe.php?cid=13025",
        "sunnyvale",
        enabled=False,
    ),
]


def active_sources() -> list[Source]:
    return [source for source in ALL_SOURCES if source.enabled]
