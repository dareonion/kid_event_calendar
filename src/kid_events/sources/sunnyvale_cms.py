"""Adapter for Sunnyvale Public Library's events calendar.

Sunnyvale publishes no machine-readable feed: its real calendar lives on a
Granicus/Vision city CMS (``library.sunnyvale.ca.gov/events/kids-events``) that
renders events as HTML and is behind Akamai bot protection — a plain HTTP fetch
(and even *headless* Chromium) gets a 403. A *headful* browser loads it fine, so
this adapter drives Playwright in headful mode to read the month grid.

Requires the optional ``sunnyvale`` extra and a Chromium install:

    uv sync --extra sunnyvale
    uv run playwright install chromium
"""

from __future__ import annotations

import contextlib
import datetime as dt
import re
from typing import Any, cast

from dateutil import parser as date_parser

from ..ages import infer_event_bands
from ..models import BAND_ORDER, AgeBand, Event
from .base import PACIFIC

BASE = "https://www.library.sunnyvale.ca.gov"
KIDS_CALENDAR = f"{BASE}/events/kids-events"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
_EVENT_ID_RE = re.compile(r"/Event/(\d+)")

# Runs in the page: read every calendar cell's date (from its aria-label) plus
# each event's time, title, and detail link.
_EXTRACT_JS = """() => {
  const items = [];
  document.querySelectorAll('td.calendar_day').forEach((td) => {
    const dateLabel = td.getAttribute('aria-label') || '';
    td.querySelectorAll('.calendar_item').forEach((item) => {
      const link = item.querySelector('a.calendar_eventlink');
      const time = item.querySelector('.calendar_eventtime');
      if (!link) return;
      items.push({
        title: (link.getAttribute('title') || link.textContent || '').trim(),
        href: link.getAttribute('href') || '',
        time: (time ? time.textContent : '').trim(),
        dateLabel,
      });
    });
  });
  return items;
}"""


class SunnyvaleCMSSource:
    key = "sunnyvale"
    name = "Sunnyvale Public Library"
    default_city = "sunnyvale"
    enabled = True

    def fetch(self, window_start: dt.datetime, window_end: dt.datetime) -> list[Event]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "Sunnyvale needs the optional extra: "
                "`uv sync --extra sunnyvale && uv run playwright install chromium`"
            ) from exc

        raw: list[dict[str, Any]] = []
        with sync_playwright() as playwright:
            # Headful: Akamai blocks headless Chromium with a 403.
            browser = playwright.chromium.launch(headless=False)
            try:
                page = browser.new_page(
                    user_agent=USER_AGENT, viewport={"width": 1280, "height": 900}
                )
                for year, month in _months_in_window(window_start, window_end):
                    page.goto(
                        f"{KIDS_CALENDAR}?curm={month}&cury={year}",
                        wait_until="domcontentloaded",
                        timeout=45000,
                    )
                    page.wait_for_selector("td.calendar_day", timeout=15000)
                    raw.extend(cast("list[dict[str, Any]]", page.evaluate(_EXTRACT_JS)))
            finally:
                browser.close()

        return parse_raw_items(raw, window_start=window_start, window_end=window_end)


def _months_in_window(start: dt.datetime, end: dt.datetime) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((year, month))
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return months


def _event_id(href: str) -> str:
    match = _EVENT_ID_RE.search(href)
    return match.group(1) if match else (href or "unknown")


def _parse_start(date_label: str, time_text: str) -> dt.datetime | None:
    # date_label looks like "Scheduled events, Tuesday, June 2, 2026".
    try:
        day = date_parser.parse(date_label, fuzzy=True).date()
    except (ValueError, OverflowError):
        return None
    moment = dt.time(0, 0)
    if time_text.strip():
        with contextlib.suppress(ValueError, OverflowError):
            moment = date_parser.parse(time_text).time()
    return dt.datetime.combine(day, moment, tzinfo=PACIFIC)


def parse_raw_items(
    items: list[dict[str, Any]],
    *,
    window_start: dt.datetime,
    window_end: dt.datetime,
    key: str = "sunnyvale",
    name: str = "Sunnyvale Public Library",
) -> list[Event]:
    """Convert scraped calendar rows into normalized events (pure)."""
    events: list[Event] = []
    seen: set[str] = set()
    for item in items:
        start = _parse_start(str(item.get("dateLabel", "")), str(item.get("time", "")))
        if start is None or not (window_start <= start <= window_end):
            continue
        href = str(item.get("href", ""))
        event_id = f"{key}:{_event_id(href)}:{start:%Y%m%dT%H%M}"
        if event_id in seen:
            continue
        seen.add(event_id)

        title = str(item.get("title", "")).strip() or "Untitled event"
        online = "online" in title.lower() or "virtual" in title.lower()
        bands = infer_event_bands(title)
        # This is the *kids* calendar view, so an event whose title implies no
        # specific age is still kid-relevant — default it to all-ages rather than
        # letting the aggregator drop it. (Adult-only titles keep their ADULT tag
        # and are still filtered out.)
        if not bands:
            bands = {AgeBand.ALL_AGES}
        url = None
        if href:
            url = href if href.startswith("http") else f"{BASE}{href}"

        events.append(
            Event(
                id=event_id,
                source=name,
                source_key=key,
                title=title,
                url=url,
                start=start,
                location_name="Online" if online else "",
                age_bands=[band for band in BAND_ORDER if band in bands],
                age_inferred=True,
            )
        )
    return events
