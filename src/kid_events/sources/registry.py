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
    # Sunnyvale has no machine-readable events feed (verified 2026-06):
    #   * sunnyvale.libcal.com is only a 3-event "featured" widget, not a
    #     subscribable calendar (ical_subscribe -> "invalid calendar id").
    #   * The real calendar lives on a Granicus/Vision CMS
    #     (library.sunnyvale.ca.gov/events) with no iCal/RSS and WAF bot
    #     protection (403 to non-browser clients).
    #   * Their BiblioCommons (sunnyvale.bibliocommons.com) is catalog-only;
    #     the events gateway returns 403.
    # Including Sunnyvale would require headless-browser scraping, so it stays
    # disabled. The URL below is a non-working placeholder.
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
