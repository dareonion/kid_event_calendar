"""The configured set of event sources.

Adding a library later is a one-line entry here that reuses an existing adapter.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

from .base import Source
from .bibliocommons import BiblioCommonsSource
from .libcal import LibCalSource
from .sunnyvale_cms import SunnyvaleCMSSource

EASTERN = ZoneInfo("America/Toronto")

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
    # Toronto Public Library is on BiblioCommons (subdomain "tpl"); it is in the
    # Eastern zone, so its local event times are tagged accordingly. It is ~2,200
    # mi from Mountain View, so the distance filter hides it unless you choose
    # "Any distance" (or favorite its branches and widen the radius).
    BiblioCommonsSource("tpl", "Toronto Public Library", "tpl", "toronto", tz=EASTERN),
    # Sunnyvale has no machine-readable feed: its real calendar is a bot-protected
    # Granicus/Vision city CMS, so this adapter scrapes it with a headful browser.
    # Requires the optional `sunnyvale` extra + `playwright install chromium`;
    # without them fetch() raises and the aggregator just reports it per-source.
    SunnyvaleCMSSource(),
]


def active_sources() -> list[Source]:
    return [source for source in ALL_SOURCES if source.enabled]
