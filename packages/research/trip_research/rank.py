"""Scoring and dedupe. Pure functions over Signals: no network, no model, no clock of their own.

`now` is always passed in and always naive UTC, matching the datetimes in the tokyo fixture. Mixing naive and
aware datetimes raises at runtime, so every source converts to naive UTC before it builds a Signal.
"""

from __future__ import annotations

import datetime as dt
import math
import re

from trip_core.models import Signal

ELLIPSIS = "..."
HALF_LIFE_DAYS = 120.0
UNKNOWN_DATE_WEIGHT = 0.3
POPULARITY_SATURATION = 3.0
RECENCY_SHARE = 0.6


def utc_now() -> dt.datetime:
    """Naive UTC. The one clock every source reads."""
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def from_epoch(seconds: float) -> dt.datetime:
    return dt.datetime.fromtimestamp(seconds, dt.UTC).replace(tzinfo=None)


def recency_weight(posted_at: dt.datetime | None, now: dt.datetime) -> float:
    """1.0 today, 0.5 at the half life, 0.59 at the 90 day mark the plan calls trendy."""
    if posted_at is None:
        return UNKNOWN_DATE_WEIGHT
    age_days = max((now - posted_at).total_seconds() / 86400.0, 0.0)
    return 0.5 ** (age_days / HALF_LIFE_DAYS)


def popularity_weight(upvotes: int, comments: int) -> float:
    """Log scale, so a 10k thread does not bury a 500 point one. Saturates around 1000 points."""
    raw = math.log10(1.0 + max(upvotes, 0) + 2.0 * max(comments, 0))
    return min(raw / POPULARITY_SATURATION, 1.0)


def score(posted_at: dt.datetime | None, now: dt.datetime, upvotes: int = 0, comments: int = 0) -> float:
    """0..1. Recency dominates because the product promise is what is good right now."""
    blended = RECENCY_SHARE * recency_weight(posted_at, now) + (1.0 - RECENCY_SHARE) * popularity_weight(
        upvotes, comments
    )
    return round(min(max(blended, 0.0), 1.0), 3)


def excerpt(text: str, limit: int) -> str:
    """Plain text, whitespace collapsed, cut on a word boundary. Never longer than `limit`, ellipsis included."""
    flat = re.sub(r"\s+", " ", text).strip()
    if len(flat) <= limit:
        return flat
    if limit <= len(ELLIPSIS):
        return flat[:limit]
    return flat[: limit - len(ELLIPSIS)].rsplit(" ", 1)[0].rstrip() + ELLIPSIS


def best_per_url(signals: list[Signal]) -> list[Signal]:
    """One signal per URL, best score, best first. The loop dedupes too; sources stay clean on their own."""
    by_url: dict[str, Signal] = {}
    for signal in signals:
        current = by_url.get(signal.url)
        if current is None or signal.score > current.score:
            by_url[signal.url] = signal
    return sorted(by_url.values(), key=lambda signal: signal.score, reverse=True)
