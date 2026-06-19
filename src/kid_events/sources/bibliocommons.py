"""Adapter for the public BiblioCommons events API.

Covers libraries on BiblioCommons (Palo Alto, Santa Clara County, San Jose) via
``https://gateway.bibliocommons.com/v2/libraries/{subdomain}/events``. Each
response carries an ``events.items`` ordering plus an ``entities`` map that
resolves audience and location ids to human-readable records. Results are
returned in chronological order across pages, so pagination stops early once a
page starts past the requested window.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from ..ages import audience_name_to_bands, infer_bands_from_title
from ..models import BAND_ORDER, AgeBand, Event
from ..textutil import html_to_text
from .base import PACIFIC

GATEWAY = "https://gateway.bibliocommons.com/v2/libraries/{subdomain}/events"
PAGE_LIMIT = 50
MAX_PAGES = 25
DEFAULT_HEADERS = {"User-Agent": "kid-events/0.1 (personal kids-event aggregator)"}


class BiblioCommonsSource:
    def __init__(
        self,
        key: str,
        name: str,
        subdomain: str,
        default_city: str,
        enabled: bool = True,
    ) -> None:
        self.key = key
        self.name = name
        self.subdomain = subdomain
        self.default_city = default_city
        self.enabled = enabled

    def fetch(
        self,
        window_start: datetime,
        window_end: datetime,
        client: httpx.Client | None = None,
    ) -> list[Event]:
        owns_client = client is None
        client = client or httpx.Client(timeout=30.0, headers=DEFAULT_HEADERS)
        url = GATEWAY.format(subdomain=self.subdomain)
        events: list[Event] = []
        try:
            page = 1
            while page <= MAX_PAGES:
                response = client.get(url, params={"limit": PAGE_LIMIT, "page": page})
                response.raise_for_status()
                payload = response.json()
                page_events = self._parse_page(payload)
                if not page_events:
                    break
                events.extend(e for e in page_events if window_start <= e.start <= window_end)
                # Pages are chronological; once a whole page starts past the
                # window there is nothing useful left to fetch.
                if min(e.start for e in page_events) > window_end:
                    break
                pagination = payload.get("events", {}).get("pagination", {})
                if page >= pagination.get("pages", page):
                    break
                page += 1
        finally:
            if owns_client:
                client.close()
        return events

    def _parse_page(self, payload: dict[str, Any]) -> list[Event]:
        return parse_page(
            payload,
            key=self.key,
            name=self.name,
            subdomain=self.subdomain,
            default_city=self.default_city,
        )


def _audience_text(audience: dict[str, Any]) -> str:
    """Clean audience label, preferring the description (e.g. SJPL has none).

    BiblioCommons groups child audiences as "Kids: Babies"; that "Kids:" prefix
    is a department grouping, not an age signal, so it is stripped to avoid a
    false school-age match.
    """
    text = audience.get("description") or audience.get("name") or ""
    if text.lower().startswith("kids:"):
        text = text.split(":", 1)[1]
    return text.strip()


def _parse_start(value: str) -> datetime:
    # Either a date ("2026-06-19") or a local datetime ("2026-06-19T10:00").
    return datetime.fromisoformat(value).replace(tzinfo=PACIFIC)


def _location_name(definition: dict[str, Any], entities: dict[str, Any]) -> str:
    branch_id = definition.get("branchLocationId")
    if branch_id:
        branch = entities.get("locations", {}).get(branch_id, {})
        if branch.get("name"):
            return str(branch["name"])
    place_id = definition.get("nonBranchLocationId")
    if place_id:
        place = entities.get("places", {}).get(place_id, {})
        if place.get("name"):
            return str(place["name"])
    return str(definition.get("locationDetails") or "")


def _registration_required(definition: dict[str, Any]) -> bool:
    info = definition.get("registrationInfo") or {}
    if info.get("provider"):
        return True
    start = info.get("registrationStart") or {}
    return bool(start.get("date"))


def parse_page(
    payload: dict[str, Any],
    *,
    key: str,
    name: str,
    subdomain: str,
    default_city: str,
) -> list[Event]:
    """Convert one BiblioCommons API page into normalized events (pure)."""
    entities = payload.get("entities", {})
    event_entities = entities.get("events", {})
    audiences = entities.get("eventAudiences", {})
    items = payload.get("events", {}).get("items", [])

    events: list[Event] = []
    for event_id in items:
        entity = event_entities.get(event_id)
        if entity is None:
            continue
        definition = entity["definition"]
        title = definition.get("title") or "Untitled event"
        description = html_to_text(definition.get("description"))

        bands: set[AgeBand] = set()
        for audience_id in definition.get("audienceIds") or []:
            audience = audiences.get(audience_id)
            if audience:
                bands |= audience_name_to_bands(_audience_text(audience))
        inferred = False
        if not bands:
            bands = infer_bands_from_title(title, description)
            inferred = bool(bands)

        events.append(
            Event(
                id=f"{key}:{event_id}",
                source=name,
                source_key=key,
                title=title,
                description=description,
                url=f"https://{subdomain}.bibliocommons.com/events/{event_id}",
                start=_parse_start(definition["start"]),
                end=_parse_start(definition["end"]) if definition.get("end") else None,
                location_name=_location_name(definition, entities),
                age_bands=[band for band in BAND_ORDER if band in bands],
                age_inferred=inferred,
                registration_required=_registration_required(definition),
                is_cancelled=bool(definition.get("isCancelled")),
            )
        )
    return events
