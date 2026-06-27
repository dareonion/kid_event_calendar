"""Command-line entry point: ``kid-events refresh`` and ``kid-events serve``."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .aggregator import aggregate
from .cache import write_cache


def cmd_refresh(args: argparse.Namespace) -> None:
    cache = aggregate(days=args.days)
    path = write_cache(cache)
    print(f"Window: {cache.window_start:%Y-%m-%d} .. {cache.window_end:%Y-%m-%d}")
    for stat in cache.sources:
        status = f"ERROR: {stat.error}" if stat.error else f"{stat.count} events"
        print(f"  {stat.name:32} {status}")
    print(f"Total kid-relevant events: {len(cache.events)}")
    for note in cache.notes:
        print(f"Note: {note}")
    print(f"Wrote {path}")


def cmd_build(args: argparse.Namespace) -> None:
    from .web.build import build_site

    out = build_site(Path(args.out))
    print(f"Built static site in {out}/ (open {out}/index.html)")


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run(
        "kid_events.web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="kid-events", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    refresh = sub.add_parser("refresh", help="Fetch sources and rebuild the event cache")
    refresh.add_argument("--days", type=int, default=14, help="Days ahead to include (default 14)")
    refresh.set_defaults(func=cmd_refresh)

    build = sub.add_parser("build", help="Render the cache into a static site (for publishing)")
    build.add_argument("--out", default="site", help="Output directory (default: site)")
    build.set_defaults(func=cmd_build)

    serve = sub.add_parser("serve", help="Run the web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    serve.add_argument("--reload", action="store_true", help="Auto-reload on code changes")
    serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
