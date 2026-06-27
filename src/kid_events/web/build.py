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
from collections import Counter
from datetime import datetime
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..branches import load_location_book
from ..cache import EventCache, load_cache
from ..geo import DEFAULT_RADIUS, RADIUS_PRESETS
from ..models import BAND_ORDER, AgeBand, Event

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

# Scripts the page can render event text in, beyond English. Backed by the
# committed (hand-authored) translations.json; unmatched text falls back to English.
TRANSLATION_LANGS = ["zh-Hant", "zh-Hans"]


@lru_cache
def load_translations() -> dict[str, dict[str, str]]:
    """English source string -> {"zh-Hant": ..., "zh-Hans": ...} (committed data)."""
    raw = files("kid_events").joinpath("data/translations.json").read_text(encoding="utf-8")
    table: dict[str, dict[str, str]] = json.loads(raw)
    return table


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
    translations = load_translations()
    metas: list[dict[str, Any]] = []
    for band in BAND_ORDER:
        meta: dict[str, Any] = {
            "value": band.value,
            "label": band.label,
            "min": band.min_months,
            "max": band.max_months,
            "is_kid": band.is_kid,
        }
        tr = translations.get(band.label, {})
        if tr.get("zh-Hant"):
            meta["label_zh_hant"] = tr["zh-Hant"]
        if tr.get("zh-Hans"):
            meta["label_zh_hans"] = tr["zh-Hans"]
        metas.append(meta)
    return metas


def branch_groups(cache: EventCache) -> list[dict[str, Any]]:
    """Distinct branches (``location_name``) grouped by library system.

    Powers the "specific library" dropdown so events can be filtered to one
    branch, not just its system. Grouped in registry (sidebar) order; sources
    with no named branch (e.g. Sunnyvale) are omitted.
    """
    counts: dict[str, Counter[str]] = {stat.name: Counter() for stat in cache.sources}
    for event in cache.events:
        if event.location_name:
            counts.setdefault(event.source, Counter())[event.location_name] += 1

    groups: list[dict[str, Any]] = []
    for stat in cache.sources:
        counter = counts.get(stat.name, Counter())
        if not counter:
            continue
        options = [{"value": name, "label": f"{name} ({n})"} for name, n in sorted(counter.items())]
        groups.append({"source": stat.name, "options": options})
    return groups


_OTHER = "__other__"


def branch_key(source_key: str, location_name: str) -> str:
    """Stable, system-scoped key for a branch (the multi-select value).

    Scoping by source avoids collisions when two systems share a branch name
    (e.g. both have a "Children's Library"). Events with no named location share
    a per-system "other" bucket so every event is selectable.
    """
    return f"{source_key}::{location_name or _OTHER}"


def library_groups(cache: EventCache) -> list[dict[str, Any]]:
    """Branches grouped by system for the multi-select "Libraries" picker.

    Every event maps to exactly one branch ``key`` here (named branch, or the
    system's "Other locations" bucket), so the picker can act as a pure
    set-membership filter. Grouped in registry (sidebar) order.
    """
    counts: dict[str, Counter[str]] = {}
    for event in cache.events:
        counts.setdefault(event.source_key, Counter())[event.location_name or _OTHER] += 1

    groups: list[dict[str, Any]] = []
    for stat in cache.sources:
        counter = counts.get(stat.key)
        if not counter:
            continue
        # Named branches alphabetically; the "other" bucket last.
        ordered = sorted(counter.items(), key=lambda kv: (kv[0] == _OTHER, kv[0].lower()))
        branches = [
            {
                "key": branch_key(stat.key, "" if name == _OTHER else name),
                "label": "Other locations" if name == _OTHER else name,
                "count": n,
            }
            for name, n in ordered
        ]
        groups.append({"source": stat.name, "source_key": stat.key, "branches": branches})
    return groups


def _event_payload(event: Event, translations: dict[str, dict[str, str]]) -> dict[str, Any]:
    """Event payload, plus a compact ``tr`` of translated title/desc when known."""
    data: dict[str, Any] = event.model_dump(mode="json")
    title_tr = translations.get(event.title, {})
    desc_tr = translations.get(event.description, {})
    tr: dict[str, dict[str, str]] = {}
    for code in TRANSLATION_LANGS:
        fields: dict[str, str] = {}
        if title_tr.get(code):
            fields["title"] = title_tr[code]
        if desc_tr.get(code):
            fields["desc"] = desc_tr[code]
        if fields:
            tr[code] = fields
    if tr:
        data["tr"] = tr
    return data


def build_payload(cache: EventCache) -> dict[str, Any]:
    """Everything the client-side filter needs, as a JSON-serializable dict."""
    book = load_location_book()
    translations = load_translations()
    reg = translations.get("registration", {})
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
        "default_units": "mi",
        "day_options": [{"value": value, "label": label} for value, label in DAY_OPTIONS],
        "default_days": DEFAULT_DAYS,
        "sources": [stat.model_dump() for stat in cache.sources],
        "notes": cache.notes,
        "events": [_event_payload(event, translations) for event in cache.events],
        # Fixed event-card labels by language (band labels travel on `bands`).
        "ui_tr": {code: {"registration": reg[code]} for code in TRANSLATION_LANGS if reg.get(code)},
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
        library_groups=library_groups(cache),
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
