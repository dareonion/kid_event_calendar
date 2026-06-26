"""FastAPI application serving the filterable kids-event page."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from ..ages import parse_age_to_months
from ..aggregator import aggregate
from ..branches import load_location_book
from ..cache import EventCache, cache_path, load_cache, write_cache
from ..filters import FilterParams, SortKey, apply_filters
from ..geo import RADIUS_PRESETS, radius_miles
from ..models import BAND_ORDER, AgeBand, Event
from ..sources.base import PACIFIC
from .build import branch_groups

MAP_EVENTS_PER_LOCATION = 25

_VALID_BAND_VALUES = {band.value for band in AgeBand}

_HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_HERE / "templates"))
templates.env.filters["day_label"] = lambda dt: dt.strftime("%a %b %-d")
templates.env.filters["time_label"] = lambda dt: dt.strftime("%-I:%M %p").lstrip("0")

# Age bands offered as explicit filter checkboxes (kid bands only).
SELECTABLE_BANDS = [band for band in BAND_ORDER if band.is_kid and band is not AgeBand.ALL_AGES]
DAY_OPTIONS = [(1, "Today"), (3, "Next 3 days"), (7, "Next 7 days"), (14, "Next 14 days")]

app = FastAPI(title="Kid Event Calendar")
app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")

# Cheap mtime-based cache reload so a `refresh` is picked up without a restart.
_state: dict[str, Any] = {"mtime": None, "cache": None}


def get_cache() -> EventCache | None:
    path = cache_path()
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    if _state["mtime"] != mtime:
        _state["cache"] = load_cache()
        _state["mtime"] = mtime
    return cast("EventCache | None", _state["cache"])


def filter_query(
    age: str = "",
    bands: list[str] = Query(default=[]),
    radius: str = "far",
    days: int = 14,
    keyword: str = "",
    sources: list[str] = Query(default=[]),
    branch: str = "",
    hide_unknown: bool = False,
    sort: str = "date",
    view: str = "list",
) -> dict[str, Any]:
    """Collect the shared filter query params for the page and event routes."""
    return {
        "age": age,
        "bands": bands,
        "radius": radius,
        "days": days,
        "keyword": keyword,
        "sources": sources,
        "branch": branch,
        "hide_unknown": hide_unknown,
        "sort": sort,
        "view": "map" if view == "map" else "list",
    }


_DEFAULT_QUERY: dict[str, Any] = {
    "age": "",
    "bands": [],
    "radius": "far",
    "days": 14,
    "keyword": "",
    "sources": [],
    "branch": "",
    "hide_unknown": False,
    "sort": "date",
    "view": "list",
}


def _build_params(query: dict[str, Any]) -> FilterParams:
    start = datetime.now(PACIFIC).replace(hour=0, minute=0, second=0, microsecond=0)
    age = str(query["age"])
    sort = query["sort"]
    valid_sort = sort if sort in (SortKey.DATE.value, SortKey.DISTANCE.value) else "date"
    return FilterParams(
        child_age_months=parse_age_to_months(age) if age.strip() else None,
        age_bands={AgeBand(b) for b in query["bands"] if b in _VALID_BAND_VALUES},
        max_miles=radius_miles(query["radius"]),
        include_unknown_location=not query["hide_unknown"],
        date_from=start,
        date_to=start + timedelta(days=query["days"]),
        keyword=str(query["keyword"]).strip(),
        sources=set(query["sources"]),
        branch=str(query["branch"]).strip(),
        sort=SortKey(valid_sort),
    )


def _selected(query: dict[str, Any]) -> dict[str, Any]:
    return {
        "age": query["age"],
        "bands": set(query["bands"]),
        "radius": query["radius"],
        "days": query["days"],
        "keyword": query["keyword"],
        "sources": set(query["sources"]),
        "branch": query["branch"],
        "hide_unknown": query["hide_unknown"],
        "sort": query["sort"],
        "view": query["view"],
    }


def _map_payload(events: list[Event], params: FilterParams) -> dict[str, Any]:
    """Group located events by point into one marker each (city centroids)."""
    book = load_location_book()
    groups: dict[tuple[float, float], dict[str, Any]] = {}
    unknown = 0
    for event in events:
        if event.lat is None or event.lon is None:
            unknown += 1
            continue
        group = groups.setdefault(
            (round(event.lat, 5), round(event.lon, 5)),
            {
                "city": event.city or "Unknown location",
                "lat": event.lat,
                "lon": event.lon,
                "events": [],
            },
        )
        group["events"].append(event)

    locations: list[dict[str, Any]] = []
    for group in groups.values():
        ordered = sorted(group["events"], key=lambda e: e.start)
        shown = ordered[:MAP_EVENTS_PER_LOCATION]
        locations.append(
            {
                "city": group["city"],
                "lat": group["lat"],
                "lon": group["lon"],
                "count": len(ordered),
                "more": len(ordered) - len(shown),
                "events": [
                    {
                        "title": e.title,
                        "when": e.start.strftime("%a %b %-d, %-I:%M %p"),
                        "url": e.url,
                    }
                    for e in shown
                ],
            }
        )
    locations.sort(key=lambda loc: loc["count"], reverse=True)
    return {
        "center": {"name": book.center_name, "lat": book.center.lat, "lon": book.center.lon},
        "radius_miles": params.max_miles,
        "locations": locations,
        "unknown": unknown,
    }


def _context(request: Request, query: dict[str, Any]) -> dict[str, Any]:
    params = _build_params(query)
    cache = get_cache()
    events = apply_filters(cache.events, params) if cache else []
    context: dict[str, Any] = {
        "request": request,
        "cache": cache,
        "events": events,
        "group_by_day": params.sort is SortKey.DATE,
        "all_bands": SELECTABLE_BANDS,
        "radius_presets": RADIUS_PRESETS,
        "day_options": DAY_OPTIONS,
        "branch_groups": branch_groups(cache) if cache else [],
        "selected": _selected(query),
    }
    if query["view"] == "map":
        context["map_data"] = _map_payload(events, params)
    return context


def _results_template(query: dict[str, Any]) -> str:
    return "_event_map.html" if query["view"] == "map" else "_event_list.html"


@app.get("/", response_class=HTMLResponse)
def index(request: Request, query: dict[str, Any] = Depends(filter_query)) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", _context(request, query))


@app.get("/events", response_class=HTMLResponse)
def events(request: Request, query: dict[str, Any] = Depends(filter_query)) -> HTMLResponse:
    return templates.TemplateResponse(request, _results_template(query), _context(request, query))


@app.post("/refresh", response_class=HTMLResponse)
async def refresh(request: Request) -> HTMLResponse:
    cache = await run_in_threadpool(aggregate)
    await run_in_threadpool(write_cache, cache)
    return templates.TemplateResponse(request, "index.html", _context(request, _DEFAULT_QUERY))
