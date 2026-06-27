# Kid Event Calendar

Aggregate upcoming **kid-friendly events** from public-library calendars (South Bay / Peninsula plus
Toronto & Mississauga) into one filterable view. Filter by a **child's age** and by **distance from any
address you choose** — type a street address, use your current location, or keep the Mountain View
default; distances and the map recenter on it.

It pulls from libraries that publish official, no-auth feeds:

| Library | Source | Status |
| --- | --- | --- |
| Palo Alto | BiblioCommons JSON API | active |
| Santa Clara County (SCCLD) | BiblioCommons JSON API | active |
| San Jose | BiblioCommons JSON API | active |
| Mountain View | LibCal iCal feed | active |
| Sunnyvale | City CMS (browser scrape) | active — needs the optional `sunnyvale` extra |
| Toronto, ON | BiblioCommons JSON API | active — far from MV (see note) |
| Mississauga, ON | ActiveCommunities (Active Network) JSON API | active — far from MV (see note) |

> **Toronto** (Toronto Public Library) is on BiblioCommons, so it slots into the
> same adapter; its events are tagged in the Eastern zone. It is ~2,200 mi from
> Mountain View, so the distance filter hides its in-person events under any
> radius preset — choose **"Any distance"** (and/or favorite its branches) to see
> them. Its online events, like any source's, still show by default.
>
> **Mississauga** (Mississauga Library) has no BiblioCommons/iCal events feed —
> its BiblioCommons catalog has the Events feature disabled. Its children's
> programs live in the City's **ActiveCommunities** (Active Network) registration
> system, whose public search API returns recurring *activities* (a season date
> range + weekday + time); the adapter expands each into the individual dated
> occurrences that fall inside the window. Also Eastern-zone and far from MV.

> **Sunnyvale** has no machine-readable feed: its `sunnyvale.libcal.com` page is
> only a 3-event "featured" widget, its BiblioCommons subdomain is catalog-only
> (events gateway 403), and its real calendar lives on a Granicus/Vision city CMS
> (`library.sunnyvale.ca.gov/events`) with no iCal/RSS that is behind Akamai bot
> protection — even *headless* Chromium gets a 403. So its adapter drives a
> **headful** browser (a Chrome window briefly opens during refresh). It needs the
> optional extra (see Setup); without it, refresh just reports Sunnyvale as errored
> and the other libraries still work.

Events are normalized into a common shape with a shared **age-band taxonomy** (infant → toddler →
preschool → school-age → tween/teen) and tagged with their **branch's coordinates** so they can be
filtered by straight-line distance from any chosen center. BiblioCommons supplies real per-branch
coordinates; Mississauga's branches come from a small committed table (`branches` in
`data/branches.json`); anything else falls back to its city centroid.

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
library, and keyword. Toggle between a **List** and a **Map** view — the map (Leaflet +
OpenStreetMap) drops one marker per branch, sized by event count, with a popup listing its events.

The **published static page** adds a **Center location** control (the `serve` app stays Mountain-View
centered): type any address or use your device location to recenter; distances, the distance-sort, and
the map all recompute from it client-side, in mi or km. Star a center to save it on your device.
Address lookups use OpenStreetMap's Nominatim; your saved addresses never leave your browser.

> Port 8000 in use? Pass another: `uv run kid-events serve --port 8001`.

The web app reads the cached `events.json`; it never fetches sources on a page load. Re-run
`kid-events refresh` (or use the **Refresh** button in the UI) to pull fresh data.

## Publishing a static page

The `serve` app needs a running server. To publish a browseable listing to a static host instead,
build a self-contained page:

```sh
uv run kid-events refresh         # produce data/cache/events.json
uv run kid-events build           # render it into ./site/
```

`build` writes `site/index.html` (plus `site/static/`), which embeds the whole event set as JSON and
does all filtering — age, distance, date, library, keyword, sort, list/map — **in the browser**, so it
works on any static host with no backend. With JavaScript disabled it degrades to a plain chronological
listing of every event.

The **Libraries** picker is a multi-select grouped by system; ★ any branches to make them favorites.
Favorites are stored in your browser (`localStorage`) and become the default selection every time you
open the page, so you can keep a short list of go-to libraries without re-filtering each visit.

### Daily GitHub Pages publish

`.github/workflows/publish.yml` refreshes and rebuilds the page every morning (Pacific) and deploys
`site/` to **GitHub Pages**, so a public URL stays current automatically. It also runs on demand
(**Actions → Publish calendar → Run workflow**) and on every push to `main`.

To enable it: in the repo's **Settings → Pages**, set **Source** to **GitHub Actions**. The published
URL is `https://<user>.github.io/<repo>/`.

> CI publishes the four feed-based libraries. **Sunnyvale** needs a headful browser (its calendar is
> bot-protected — see above), which the GitHub runner can't provide, so it is reported as errored in the
> sidebar and skipped. Run `refresh` + `build` locally with the `sunnyvale` extra to include it.

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
