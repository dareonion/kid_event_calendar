"""Adapter for LibCal (Springshare) iCal feeds.

LibCal exposes a per-calendar iCal feed at
``https://{subdomain}.libcal.com/ical_subscribe.php?cid={cid}``. Unlike
BiblioCommons, the feed does *not* include a structured audience field — the
``CATEGORIES`` property carries the event *type* (e.g. "Storytime",
"Arts & Crafts (Youth)"). Age bands are therefore inferred from the summary,
categories, and description, and every LibCal event is flagged ``age_inferred``.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, cast

import httpx
from icalendar import Calendar

from ..ages import infer_event_bands
from ..models import BAND_ORDER, Event
from ..textutil import html_to_text
from .base import PACIFIC

DEFAULT_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; kid-events/0.1)"}


class LibCalSource:
    def __init__(
        self,
        key: str,
        name: str,
        ical_url: str,
        default_city: str,
        enabled: bool = True,
    ) -> None:
        self.key = key
        self.name = name
        self.ical_url = ical_url
        self.default_city = default_city
        self.enabled = enabled

    def fetch(
        self,
        window_start: dt.datetime,
        window_end: dt.datetime,
        client: httpx.Client | None = None,
    ) -> list[Event]:
        owns_client = client is None
        client = client or httpx.Client(
            timeout=30.0, headers=DEFAULT_HEADERS, follow_redirects=True
        )
        try:
            response = client.get(self.ical_url)
            response.raise_for_status()
            events = parse_ical(
                response.text, key=self.key, name=self.name, default_city=self.default_city
            )
        finally:
            if owns_client:
                client.close()
        return [e for e in events if window_start <= e.start <= window_end]


def _to_pacific(value: dt.date | dt.datetime) -> dt.datetime:
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=PACIFIC)
        return value.astimezone(PACIFIC)
    return dt.datetime(value.year, value.month, value.day, tzinfo=PACIFIC)


def _categories(component: Any) -> list[str]:
    raw = component.get("CATEGORIES")
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out: list[str] = []
    for item in items:
        for cat in getattr(item, "cats", []):
            text = str(cat).strip()
            if text:
                out.append(text)
    return out


def parse_ical(text: str, *, key: str, name: str, default_city: str) -> list[Event]:
    """Convert a LibCal iCal feed into normalized events (pure)."""
    calendar = Calendar.from_ical(text)
    events: list[Event] = []
    # icalendar components are typed but expose an untyped .get(); treat as Any.
    for component in cast("list[Any]", calendar.walk("VEVENT")):
        dtstart = component.get("DTSTART")
        if dtstart is None:
            continue
        start = _to_pacific(dtstart.dt)
        dtend = component.get("DTEND")
        end = _to_pacific(dtend.dt) if dtend is not None else None

        summary = str(component.get("SUMMARY") or "Untitled event")
        description = html_to_text(str(component.get("DESCRIPTION") or ""))
        location = str(component.get("LOCATION") or "")
        url = str(component.get("URL")) if component.get("URL") else None
        uid = str(component.get("UID") or url or summary)
        categories = _categories(component)

        bands = infer_event_bands(summary, description, tuple(categories))
        lowered_desc = description.lower()
        registration = (
            "registration is required" in lowered_desc or "registration required" in lowered_desc
        )
        status = str(component.get("STATUS") or "").upper()

        events.append(
            Event(
                id=f"{key}:{uid}:{start:%Y%m%dT%H%M}",
                source=name,
                source_key=key,
                title=summary,
                description=description,
                url=url,
                start=start,
                end=end,
                location_name=location,
                age_bands=[band for band in BAND_ORDER if band in bands],
                age_inferred=True,
                registration_required=registration,
                is_cancelled=status == "CANCELLED",
            )
        )
    return events
