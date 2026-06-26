"""Render the cached events into a self-contained static site.

The live app (:mod:`kid_events.web.app`) filters server-side via HTMX, which
needs a running server. For a page that can be *published* (e.g. to GitHub Pages
on a daily schedule) we instead emit a single static ``index.html`` that embeds
the whole event set as JSON and filters entirely in the browser
(``static/app.js``). The data window is fixed at build time; re-running the build
each day keeps the published listing current.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..branches import load_location_book
from ..cache import EventCache, load_cache
from ..geo import DEFAULT_RADIUS, RADIUS_PRESETS
from ..models import BAND_ORDER, AgeBand

_HERE = Path(__file__).resolve().parent
_TEMPLATES = _HERE / "templates"
_STATIC = _HERE / "static"

# Assets the static page needs (htmx and the server-only bits are omitted).
_ASSETS = ["style.css", "leaflet.css", "leaflet.js", "map.js", "app.js"]

# Kid age bands offered as explicit filter checkboxes (mirrors the live app).
SELECTABLE_BANDS = [band for band in BAND_ORDER if band.is_kid and band is not AgeBand.ALL_AGES]
DAY_OPTIONS: list[tuple[int, str]] = [
    (1, "Today"),
    (3, "Next 3 days"),
    (7, "Next 7 days"),
    (14, "Next 14 days"),
]
DEFAULT_DAYS = 14


def _day_label(value: datetime) -> str:
    return value.strftime("%a %b %-d")


def _time_label(value: datetime) -> str:
    return value.strftime("%-I:%M %p").lstrip("0")


def _environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["day_label"] = _day_label
    env.filters["time_label"] = _time_label
    return env


def _band_meta() -> list[dict[str, Any]]:
    """Per-band ranges/labels the browser needs to map an age to bands."""
    return [
        {
            "value": band.value,
            "label": band.label,
            "min": band.min_months,
            "max": band.max_months,
            "is_kid": band.is_kid,
        }
        for band in BAND_ORDER
    ]


def build_payload(cache: EventCache) -> dict[str, Any]:
    """Everything the client-side filter needs, as a JSON-serializable dict."""
    book = load_location_book()
    return {
        "generated_at": cache.generated_at.isoformat(),
        "generated_label": f"{_day_label(cache.generated_at)}, {_time_label(cache.generated_at)}",
        "window_start": cache.window_start.isoformat(),
        "window_end": cache.window_end.isoformat(),
        "center": {"name": book.center_name, "lat": book.center.lat, "lon": book.center.lon},
        "bands": _band_meta(),
        "radius_presets": [
            {"key": key, "label": label, "miles": miles}
            for key, (label, miles) in RADIUS_PRESETS.items()
        ],
        "default_radius": DEFAULT_RADIUS,
        "day_options": [{"value": value, "label": label} for value, label in DAY_OPTIONS],
        "default_days": DEFAULT_DAYS,
        "sources": [stat.model_dump() for stat in cache.sources],
        "notes": cache.notes,
        "events": [event.model_dump(mode="json") for event in cache.events],
    }


def render_index(cache: EventCache) -> str:
    """Render the standalone static page for the given cache."""
    payload = build_payload(cache)
    # Embed as JSON in a <script> block. Escaping ``<`` keeps a literal
    # ``</script>`` in any field from prematurely closing the tag.
    data_json = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    env = _environment()
    template = env.get_template("static_index.html")
    return template.render(
        generated_label=payload["generated_label"],
        selectable_bands=SELECTABLE_BANDS,
        radius_presets=RADIUS_PRESETS,
        default_radius=DEFAULT_RADIUS,
        day_options=DAY_OPTIONS,
        default_days=DEFAULT_DAYS,
        sources=cache.sources,
        notes=cache.notes,
        # The <noscript> fallback lists every event, chronologically.
        events=sorted(cache.events, key=lambda event: event.start),
        group_by_day=True,
        data_json=data_json,
    )


def build_site(out_dir: Path, cache: EventCache | None = None) -> Path:
    """Write ``index.html`` plus static assets into ``out_dir``; return the dir.

    Reads the on-disk cache when one is not supplied; raises if neither exists.
    """
    if cache is None:
        cache = load_cache()
    if cache is None:
        raise FileNotFoundError("No event cache to build from. Run `kid-events refresh` first.")

    out_dir = Path(out_dir)
    static_out = out_dir / "static"
    static_out.mkdir(parents=True, exist_ok=True)
    for asset in _ASSETS:
        shutil.copyfile(_STATIC / asset, static_out / asset)

    (out_dir / "index.html").write_text(render_index(cache), encoding="utf-8")
    # Tell GitHub Pages not to run the output through Jekyll.
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    return out_dir
