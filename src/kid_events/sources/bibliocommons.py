"""Adapter for the public BiblioCommons events API.

Covers libraries on BiblioCommons (Palo Alto, Santa Clara County, San Jose) via
``https://gateway.bibliocommons.com/v2/libraries/{subdomain}/events``. Each
response carries an ``events.items`` list plus an ``entities`` map that resolves
audience and location ids to human-readable records.

The API exposes no working date filter and ``events.items`` is NOT in date
order (a single page can span many months), so in-window events are scattered
across all pages. We therefore page through the whole result set (at a large
limit to keep the request count down) and keep only events inside the window.
"""

from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, tzinfo
from typing import Any, cast

import httpx

from ..ages import audience_name_to_bands, infer_bands_from_title
from ..models import BAND_ORDER, AgeBand, Event
from ..textutil import html_to_text
from .base import PACIFIC

GATEWAY = "https://gateway.bibliocommons.com/v2/libraries/{subdomain}/events"
PAGE_LIMIT = 100  # 200+ intermittently 500s on the larger libraries
MAX_PAGES = 80  # safety cap; covers the largest library (~8k events at this limit)
WORKERS = 8  # parallel page fetches per library
RETRIES = 2  # the gateway returns occasional transient 500s
DEFAULT_HEADERS = {"User-Agent": "kid-events/0.1 (personal kids-event aggregator)"}


class BiblioCommonsSource:
    def __init__(
        self,
        key: str,
        name: str,
        subdomain: str,
        default_city: str,
        enabled: bool = True,
        tz: tzinfo = PACIFIC,
    ) -> None:
        self.key = key
        self.name = name
        self.subdomain = subdomain
        self.default_city = default_city
        self.enabled = enabled
        # BiblioCommons returns each event's local wall-clock time without an
        # offset; tag it with the library's own zone (e.g. Eastern for Toronto).
        self.tz = tz

    def fetch(
        self,
        window_start: datetime,
        window_end: datetime,
        client: httpx.Client | None = None,
    ) -> list[Event]:
        owns_client = client is None
        client = client or httpx.Client(timeout=30.0, headers=DEFAULT_HEADERS)
        url = GATEWAY.format(subdomain=self.subdomain)
        try:
            # The whole result set must be scanned (items aren't date-ordered),
            # so fetch page 1 to learn the page count, then pull the rest in
            # parallel — httpx.Client is safe to share across threads.
            first = _get_page(client, url, 1)
            total_pages = first.get("events", {}).get("pagination", {}).get("pages", 1)
            payloads = [first]
            remaining = range(2, min(total_pages, MAX_PAGES) + 1)
            if remaining:
                with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                    payloads.extend(pool.map(lambda p: _get_page(client, url, p), remaining))
        finally:
            if owns_client:
                client.close()

        events: list[Event] = []
        for payload in payloads:
            events.extend(
                e for e in self._parse_page(payload) if window_start <= e.start <= window_end
            )
        return events

    def _parse_page(self, payload: dict[str, Any]) -> list[Event]:
        return parse_page(
            payload,
            key=self.key,
            name=self.name,
            subdomain=self.subdomain,
            default_city=self.default_city,
            tz=self.tz,
        )


def _get_page(client: httpx.Client, url: str, page: int) -> dict[str, Any]:
    """GET one page, retrying the gateway's occasional transient 500s."""
    params = {"limit": PAGE_LIMIT, "page": page}
    for attempt in range(RETRIES + 1):
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            return cast("dict[str, Any]", response.json())
        except (httpx.HTTPStatusError, httpx.TransportError):
            if attempt == RETRIES:
                raise
            time.sleep(0.6 * (attempt + 1))
    raise AssertionError("unreachable")  # pragma: no cover


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


def _parse_start(value: str, tz: tzinfo = PACIFIC) -> datetime:
    # Either a date ("2026-06-19") or a local datetime ("2026-06-19T10:00").
    return datetime.fromisoformat(value).replace(tzinfo=tz)


def _coord(value: Any) -> float | None:
    """A finite, non-zero coordinate, else None."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if math.isfinite(number) and number != 0:
            return number
    return None


def _resolve_location(
    definition: dict[str, Any], entities: dict[str, Any]
) -> tuple[str, float | None, float | None, str]:
    """Return ``(name, lat, lon, city)`` for an event's location.

    A branch entity carries a real point in ``mapLocation.centrePoint`` plus a
    structured ``address`` — trust the point whenever it has finite, non-zero
    lat/lng (``isGeocoded`` is unreliable and is deliberately ignored). Non-branch
    places and free-text details have no coordinates.
    """
    branch_id = definition.get("branchLocationId")
    if branch_id:
        branch = entities.get("locations", {}).get(branch_id, {})
        name = str(branch.get("name") or "")
        if name:
            point = (branch.get("mapLocation") or {}).get("centrePoint") or {}
            lat, lon = _coord(point.get("lat")), _coord(point.get("lng"))
            if lat is None or lon is None:
                lat = lon = None
            city = str((branch.get("address") or {}).get("city") or "").strip().title()
            return name, lat, lon, city
    place_id = definition.get("nonBranchLocationId")
    if place_id:
        place = entities.get("places", {}).get(place_id, {})
        if place.get("name"):
            return str(place["name"]), None, None, ""
    return str(definition.get("locationDetails") or ""), None, None, ""


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
    tz: tzinfo = PACIFIC,
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

        loc_name, lat, lon, city = _resolve_location(definition, entities)
        events.append(
            Event(
                id=f"{key}:{event_id}",
                source=name,
                source_key=key,
                title=title,
                description=description,
                url=f"https://{subdomain}.bibliocommons.com/events/{event_id}",
                start=_parse_start(definition["start"], tz),
                end=_parse_start(definition["end"], tz) if definition.get("end") else None,
                location_name=loc_name,
                lat=lat,
                lon=lon,
                city=city,
                geo_precise=lat is not None and lon is not None,
                age_bands=[band for band in BAND_ORDER if band in bands],
                age_inferred=inferred,
                registration_required=_registration_required(definition),
                is_cancelled=bool(definition.get("isCancelled")),
            )
        )
    return events
