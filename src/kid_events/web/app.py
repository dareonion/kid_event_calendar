"""FastAPI application serving the filterable kids-event page."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from ..ages import parse_age_to_months
from ..aggregator import aggregate
from ..cache import EventCache, cache_path, load_cache, write_cache
from ..filters import FilterParams, SortKey, apply_filters
from ..geo import RADIUS_PRESETS, radius_miles
from ..models import BAND_ORDER, AgeBand
from ..sources.base import PACIFIC

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


def _build_params(
    age: str,
    bands: list[str],
    radius: str,
    days: int,
    keyword: str,
    sources: list[str],
    hide_unknown: bool,
    sort: str,
) -> FilterParams:
    start = datetime.now(PACIFIC).replace(hour=0, minute=0, second=0, microsecond=0)
    child_age = parse_age_to_months(age) if age.strip() else None
    selected_bands = {AgeBand(b) for b in bands if b in _VALID_BAND_VALUES}
    valid_sort = sort if sort in (SortKey.DATE.value, SortKey.DISTANCE.value) else "date"
    return FilterParams(
        child_age_months=child_age,
        age_bands=selected_bands,
        max_miles=radius_miles(radius),
        include_unknown_location=not hide_unknown,
        date_from=start,
        date_to=start + timedelta(days=days),
        keyword=keyword.strip(),
        sources=set(sources),
        sort=SortKey(valid_sort),
    )


def _context(request: Request, params: FilterParams, *, selected: dict[str, Any]) -> dict[str, Any]:
    cache = get_cache()
    events = apply_filters(cache.events, params) if cache else []
    return {
        "request": request,
        "cache": cache,
        "events": events,
        "group_by_day": params.sort is SortKey.DATE,
        "all_bands": SELECTABLE_BANDS,
        "radius_presets": RADIUS_PRESETS,
        "day_options": DAY_OPTIONS,
        "selected": selected,
    }


def _selected(
    age: str,
    bands: list[str],
    radius: str,
    days: int,
    keyword: str,
    sources: list[str],
    hide_unknown: bool,
    sort: str,
) -> dict[str, Any]:
    return {
        "age": age,
        "bands": set(bands),
        "radius": radius,
        "days": days,
        "keyword": keyword,
        "sources": set(sources),
        "hide_unknown": hide_unknown,
        "sort": sort,
    }


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    age: str = "",
    bands: list[str] = Query(default=[]),
    radius: str = "far",
    days: int = 14,
    keyword: str = "",
    sources: list[str] = Query(default=[]),
    hide_unknown: bool = False,
    sort: str = "date",
) -> HTMLResponse:
    params = _build_params(age, bands, radius, days, keyword, sources, hide_unknown, sort)
    selected = _selected(age, bands, radius, days, keyword, sources, hide_unknown, sort)
    return templates.TemplateResponse(
        request, "index.html", _context(request, params, selected=selected)
    )


@app.get("/events", response_class=HTMLResponse)
def events(
    request: Request,
    age: str = "",
    bands: list[str] = Query(default=[]),
    radius: str = "far",
    days: int = 14,
    keyword: str = "",
    sources: list[str] = Query(default=[]),
    hide_unknown: bool = False,
    sort: str = "date",
) -> HTMLResponse:
    params = _build_params(age, bands, radius, days, keyword, sources, hide_unknown, sort)
    selected = _selected(age, bands, radius, days, keyword, sources, hide_unknown, sort)
    return templates.TemplateResponse(
        request, "_event_list.html", _context(request, params, selected=selected)
    )


@app.post("/refresh", response_class=HTMLResponse)
async def refresh(request: Request) -> HTMLResponse:
    cache = await run_in_threadpool(aggregate)
    await run_in_threadpool(write_cache, cache)
    params = _build_params("", [], "far", 14, "", [], False, "date")
    selected = _selected("", [], "far", 14, "", [], False, "date")
    return templates.TemplateResponse(
        request, "index.html", _context(request, params, selected=selected)
    )
