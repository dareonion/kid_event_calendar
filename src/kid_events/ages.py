"""Map free-text audience labels and child ages onto the canonical age bands.

Both the BiblioCommons and LibCal adapters tag events with human-readable
audience strings (e.g. "Babies (under 2)", "Pre-schoolers (3-5)", "Toddlers").
:func:`audience_name_to_bands` is the single shared mapper they both use, so the
two sources end up speaking the same age vocabulary.
"""

from __future__ import annotations

import re

from .models import AgeBand

# Ordered (keyword, band) pairs. Matching is plain case-insensitive substring,
# so keywords are chosen to avoid collisions (e.g. we never match a bare
# "school" because it is a substring of "preschool").
_AUDIENCE_KEYWORDS: list[tuple[str, AgeBand]] = [
    # Infants
    ("baby", AgeBand.INFANT),
    ("babies", AgeBand.INFANT),
    ("infant", AgeBand.INFANT),
    ("newborn", AgeBand.INFANT),
    ("lapsit", AgeBand.INFANT),
    ("lap sit", AgeBand.INFANT),
    ("lap-sit", AgeBand.INFANT),
    ("under 2", AgeBand.INFANT),
    # Toddlers
    ("toddler", AgeBand.TODDLER),
    ("walker", AgeBand.TODDLER),
    # Preschool
    ("preschool", AgeBand.PRESCHOOL),
    ("pre-school", AgeBand.PRESCHOOL),
    ("pre school", AgeBand.PRESCHOOL),
    ("pre-k", AgeBand.PRESCHOOL),
    ("prek", AgeBand.PRESCHOOL),
    # School age
    ("school age", AgeBand.SCHOOL_AGE),
    ("school-age", AgeBand.SCHOOL_AGE),
    ("grade school", AgeBand.SCHOOL_AGE),
    ("elementary", AgeBand.SCHOOL_AGE),
    ("big kid", AgeBand.SCHOOL_AGE),
    ("kids", AgeBand.SCHOOL_AGE),
    ("children", AgeBand.SCHOOL_AGE),
    # Tween / teen
    ("tween", AgeBand.TWEEN_TEEN),
    ("teen", AgeBand.TWEEN_TEEN),
    ("middle school", AgeBand.TWEEN_TEEN),
    ("high school", AgeBand.TWEEN_TEEN),
    # Adult
    ("adult", AgeBand.ADULT),
    ("parent", AgeBand.ADULT),
    ("senior", AgeBand.ADULT),
    ("grown", AgeBand.ADULT),
    # All ages / family
    ("all ages", AgeBand.ALL_AGES),
    ("all-ages", AgeBand.ALL_AGES),
    ("family", AgeBand.ALL_AGES),
    ("families", AgeBand.ALL_AGES),
    ("everyone", AgeBand.ALL_AGES),
    ("intergenerational", AgeBand.ALL_AGES),
]


def audience_name_to_bands(text: str) -> set[AgeBand]:
    """Return every age band implied by an audience label / free text."""
    lowered = text.lower()
    return {band for keyword, band in _AUDIENCE_KEYWORDS if keyword in lowered}


def infer_bands_from_title(title: str, description: str = "") -> set[AgeBand]:
    """Best-effort age guess for events that carry no explicit audience tag.

    Used as a fallback only; callers should flag results as inferred.
    """
    text = f"{title}\n{description}"
    bands = audience_name_to_bands(text)
    lowered = text.lower()
    if "storytime" in lowered or "story time" in lowered:
        bands |= {AgeBand.INFANT, AgeBand.TODDLER, AgeBand.PRESCHOOL}
    return bands


def child_age_to_bands(age_months: int) -> set[AgeBand]:
    """Bands a child of the given age (in months) would be a fit for.

    Always includes :attr:`AgeBand.ALL_AGES` so family / all-ages events match.
    """
    bands = {
        band for band in AgeBand if band.is_kid and band.min_months <= age_months <= band.max_months
    }
    bands.add(AgeBand.ALL_AGES)
    return bands


_AGE_RE = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>months?|mos?|mths?|m|years?|yrs?|y)?", re.IGNORECASE
)


def parse_age_to_months(text: str) -> int | None:
    """Parse a human age like '8 months', '2y', '18mo', '3' into whole months.

    A bare number with no unit is interpreted as years (the common case, e.g.
    "age 4"). Returns ``None`` if nothing parseable is found.
    """
    match = _AGE_RE.search(text.strip())
    if match is None:
        return None
    value = float(match.group("num"))
    unit = (match.group("unit") or "").lower()
    if unit.startswith("m"):
        return round(value)
    return round(value * 12)
