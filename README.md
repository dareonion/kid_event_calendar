# Kid Event Calendar

Aggregate upcoming **kid-friendly events** from South Bay / Peninsula public-library calendars into one
filterable view. Filter by a **child's age** and by **how far you're willing to drive from Mountain
View, CA**.

It pulls from libraries that publish official, no-auth feeds:

| Library | Source | Status |
| --- | --- | --- |
| Palo Alto | BiblioCommons JSON API | active |
| Santa Clara County (SCCLD) | BiblioCommons JSON API | active |
| San Jose | BiblioCommons JSON API | active |
| Mountain View | LibCal iCal feed | active |
| Sunnyvale | City CMS (browser scrape) | active — needs the optional `sunnyvale` extra |

> **Sunnyvale** has no machine-readable feed: its `sunnyvale.libcal.com` page is
> only a 3-event "featured" widget, its BiblioCommons subdomain is catalog-only
> (events gateway 403), and its real calendar lives on a Granicus/Vision city CMS
> (`library.sunnyvale.ca.gov/events`) with no iCal/RSS that is behind Akamai bot
> protection — even *headless* Chromium gets a 403. So its adapter drives a
> **headful** browser (a Chrome window briefly opens during refresh). It needs the
> optional extra (see Setup); without it, refresh just reports Sunnyvale as errored
> and the other four libraries still work.

Events are normalized into a common shape with a shared **age-band taxonomy** (infant → toddler →
preschool → school-age → tween/teen) and tagged with their library branch's location so they can be
filtered by straight-line distance from a center point.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Setup

```sh
uv sync
```

To also pull **Sunnyvale** (optional; drives a headful browser — see the note above):

```sh
uv sync --extra sunnyvale
uv run playwright install chromium
```

## Usage

```sh
# Fetch + normalize events from all sources into data/cache/events.json
uv run kid-events refresh

# Start the web app at http://localhost:8000
uv run kid-events serve
```

Open <http://localhost:8000> and use the sidebar to filter by child age, distance radius, date range,
source library, and keyword.

The web app reads the cached `events.json`; it never fetches sources on a page load. Re-run
`kid-events refresh` (or use the **Refresh** button in the UI) to pull fresh data.

## Development

```sh
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy src            # type-check
uv run pytest              # tests
uv run pre-commit install  # enable git hooks
```

## Roadmap (v2)

- Map of playgrounds / play structures / swings / sandboxes (OpenStreetMap Overpass + Leaflet).
- More sources: Santa Clara City library, Active.com parks & rec, museums, kid aggregators.
- Real drive-time distances instead of straight-line radius.
