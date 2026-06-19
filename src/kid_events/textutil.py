"""Small text helpers shared by source adapters and the web layer."""

from __future__ import annotations

import html
import re

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def html_to_text(value: str | None) -> str:
    """Strip HTML tags, unescape entities, and collapse whitespace."""
    if not value:
        return ""
    text = _TAG_RE.sub(" ", value)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def truncate(value: str, limit: int = 240) -> str:
    """Trim text to ``limit`` characters on a word boundary with an ellipsis."""
    value = value.strip()
    if len(value) <= limit:
        return value
    clipped = value[:limit].rsplit(" ", 1)[0].rstrip()
    return f"{clipped}…"
