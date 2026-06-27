"""Adapter for an ActiveCommunities (Active Network) program registry.

Used for **Mississauga Library**, which publishes no BiblioCommons/iCal events
feed — its children's programs live in the City's ActiveCommunities registration
system (the "Active Mississauga" site). Its public activity-search REST endpoint
returns recurring *activities* (a season ``date_range`` + ``days_of_week`` +
``time_range``), which we expand into individual dated occurrences inside the
requested window so they read like every other source's per-occurrence events.

The endpoint is a plain JSON POST needing no auth or cookies::

    POST {base}/rest/activities/list?locale=en-US

with a ``page_info`` header carrying pagination. ``date_after`` / ``date_before``
scope the result to the window server-side.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any, cast

import httpx

from ..models import BAND_ORDER, AgeBand, Event
from ..textutil import html_to_text
from .base import PACIFIC

PAGE_SIZE = 20
MAX_PAGES = 40  # safety cap; a 2-week window is well under this
DEFAULT_HEADERS = {"User-Agent": "kid-events/0.1 (personal kids-event aggregator)"}

_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


class ActiveCommunitiesSource:
    def __init__(
        self,
        key: str,
        name: str,
        base_url: str,
        department_ids: list[str],
        default_city: str,
        tz: tzinfo = PACIFIC,
        enabled: bool = True,
    ) -> None:
        self.key = key
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.department_ids = list(department_ids)
        self.default_city = default_city
        self.tz = tz
        self.enabled = enabled

    def fetch(
        self,
        window_start: datetime,
        window_end: datetime,
        client: httpx.Client | None = None,
    ) -> list[Event]:
        owns_client = client is None
        client = client or httpx.Client(timeout=30.0, headers=DEFAULT_HEADERS)
        url = f"{self.base_url}/rest/activities/list?locale=en-US"
        try:
            first = self._get_page(client, url, 1, window_start, window_end)
            total_pages = first.get("headers", {}).get("page_info", {}).get("total_page", 1)
            items = list(first.get("body", {}).get("activity_items", []))
            for page in range(2, min(total_pages, MAX_PAGES) + 1):
                payload = self._get_page(client, url, page, window_start, window_end)
                items.extend(payload.get("body", {}).get("activity_items", []))
        finally:
            if owns_client:
                client.close()

        return parse_activities(
            items,
            key=self.key,
            name=self.name,
            default_city=self.default_city,
            tz=self.tz,
            window_start=window_start,
            window_end=window_end,
        )

    def _search_pattern(self, window_start: datetime, window_end: datetime) -> dict[str, Any]:
        return {
            "activity_select_param": 2,
            "activity_department_ids": self.department_ids,
            "activity_keyword": "",
            "center_ids": [],
            "activity_category_ids": [],
            "activity_other_category_ids": [],
            "activity_type_ids": [],
            "site_ids": [],
            "season_ids": [],
            "child_season_ids": [],
            "geographic_area_ids": [],
            "instructor_ids": [],
            "skills": [],
            "days_of_week": None,
            "min_age": None,
            "max_age": None,
            "time_after_str": "",
            "date_after": window_start.date().isoformat(),
            "date_before": window_end.date().isoformat(),
            "for_map": False,
            "custom_price_from": "",
            "custom_price_to": "",
            "activity_id": None,
        }

    def _get_page(
        self,
        client: httpx.Client,
        url: str,
        page: int,
        window_start: datetime,
        window_end: datetime,
    ) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "page_info": json.dumps(
                {"order_by": "", "page_number": page, "total_records_per_page": PAGE_SIZE}
            ),
        }
        body = {
            "activity_search_pattern": self._search_pattern(window_start, window_end),
            "activity_transfer_pattern": {},
        }
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        return cast("dict[str, Any]", response.json())


def _age_months(year: Any, month: Any, week: Any) -> int:
    return (year or 0) * 12 + (month or 0) + round((week or 0) / 4.345)


def age_range_to_bands(min_months: int, max_months: int) -> set[AgeBand]:
    """Kid bands a ``[min, max]`` month range overlaps (excludes adult/all-ages)."""
    return {
        band
        for band in AgeBand
        if band.is_kid
        and band is not AgeBand.ALL_AGES
        and band.min_months <= max_months
        and band.max_months >= min_months
    }


def bands_for_item(item: dict[str, Any]) -> list[AgeBand]:
    """Age bands for one activity, in display order.

    ActiveNet uses an all-zero age range as the "all ages" sentinel; a bounded
    range maps to whichever kid bands it overlaps (an adult-only range yields
    none, so the aggregator drops it as not kid-relevant).
    """
    min_months = _age_months(
        item.get("age_min_year"), item.get("age_min_month"), item.get("age_min_week")
    )
    max_months = _age_months(
        item.get("age_max_year"), item.get("age_max_month"), item.get("age_max_week")
    )
    if min_months == 0 and max_months == 0:
        return [AgeBand.ALL_AGES]
    bands = age_range_to_bands(min_months, max_months)
    return [band for band in BAND_ORDER if band in bands]


def _parse_time(time_range: str) -> tuple[time | None, time | None]:
    """Parse ``"1:30 PM - 2:15 PM"`` into ``(start, end)`` times."""

    def one(text: str) -> time | None:
        try:
            return datetime.strptime(text.strip(), "%I:%M %p").time()
        except ValueError:
            return None

    parts = [p for p in time_range.split("-") if p.strip()]
    start = one(parts[0]) if parts else None
    end = one(parts[1]) if len(parts) > 1 else None
    return start, end


def _occurrence_dates(
    item: dict[str, Any], window_start: datetime, window_end: datetime
) -> list[date]:
    """Expand a recurring activity into in-window meeting dates."""
    try:
        season_start = date.fromisoformat(item["date_range_start"])
    except (KeyError, ValueError):
        return []
    raw_end = item.get("date_range_end")
    season_end = date.fromisoformat(raw_end) if raw_end else season_start

    win_lo, win_hi = window_start.date(), window_end.date()
    if item.get("only_one_day"):
        return [season_start] if win_lo <= season_start <= win_hi else []

    days = {
        _WEEKDAYS[token.strip()[:3].lower()]
        for token in (item.get("days_of_week") or "").split(",")
        if token.strip()[:3].lower() in _WEEKDAYS
    }
    if not days:  # no weekday given: assume it meets on the season's start weekday
        days = {season_start.weekday()}

    lo, hi = max(season_start, win_lo), min(season_end, win_hi)
    out: list[date] = []
    current = lo
    while current <= hi:
        if current.weekday() in days:
            out.append(current)
        current += timedelta(days=1)
    return out


def parse_activities(
    items: list[dict[str, Any]],
    *,
    key: str,
    name: str,
    default_city: str,
    tz: tzinfo,
    window_start: datetime,
    window_end: datetime,
) -> list[Event]:
    """Convert ActiveCommunities activities into normalized, dated events (pure)."""
    events: list[Event] = []
    for item in items:
        bands = bands_for_item(item)
        if not bands:  # adult-only / no kid relevance — let the aggregator-free path skip it
            continue
        start_time, end_time = _parse_time(item.get("time_range") or "")
        if start_time is None:
            start_time = time(0, 0)
        location = (item.get("location") or {}).get("label") or ""
        description = html_to_text(item.get("desc"))
        url = item.get("detail_url") or None
        registration = not bool(item.get("allow_drop_in_reg"))

        for day in _occurrence_dates(item, window_start, window_end):
            start = datetime.combine(day, start_time, tzinfo=tz)
            end = datetime.combine(day, end_time, tzinfo=tz) if end_time else None
            events.append(
                Event(
                    id=f"{key}:{item.get('id')}:{day.isoformat()}",
                    source=name,
                    source_key=key,
                    title=item.get("name") or "Untitled program",
                    description=description,
                    url=url,
                    start=start,
                    end=end,
                    location_name=location,
                    age_bands=bands,
                    registration_required=registration,
                )
            )
    return events
