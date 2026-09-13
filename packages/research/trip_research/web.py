"""Exa web search to Signals.

Was scoped to reddit.com via `includeDomains` to read Reddit content without calling Reddit's own API (their
Responsible Builder Policy needs approval we do not have and restricts sharing post data with third-party AI).
Verified live on 2026-09-13: `includeDomains: ["reddit.com"]` returns zero results every time, while the same
call against a control domain (wikipedia.org, nytimes.com) returns results normally. Not documented anywhere,
found by direct testing. So this source is general open-web travel content, not a Reddit channel; a result is
still labelled by the host it came from in case Reddit content ever surfaces unrestricted, but that has not been
observed. Getting real Reddit content back requires either Reddit's own approval or a different provider.

search() never raises. The loop runs research with retries=0 and no try (apps/agent/trip_agent/loop.py).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
from typing import Any
from urllib.parse import urlparse

import httpx

from trip_core.models import Signal, SignalSource, ToolError, TripBrief
from trip_research.http import check_status
from trip_research.places import extract_places
from trip_research.rank import best_per_url, excerpt, score, to_naive_utc, utc_now

SEARCH_URL = "https://api.exa.ai/search"
EXCERPT_CHARS = 400
TEXT_CHARS = 1200
PER_QUERY = 25
LOOKBACK_DAYS = 730


def queries(brief: TripBrief) -> list[str]:
    """Two per brief. Deterministic, so cassettes stay stable and the bill stays predictable."""
    terms = [f"best things to do in {brief.destination}"]
    if brief.styles:
        terms.append(f"{brief.destination} {brief.styles[0]} recommendations")
    return terms


def source_for(url: str) -> SignalSource:
    host = (urlparse(url).hostname or "").lower()
    return SignalSource.reddit if host == "reddit.com" or host.endswith(".reddit.com") else SignalSource.web


def signal_id(url: str) -> str:
    return f"ex-{hashlib.sha256(url.encode()).hexdigest()[:10]}"


def to_signals(payload: dict[str, Any], destination: str, now: dt.datetime) -> list[Signal]:
    """Pure. Exa has no popularity metric and documents no score field, so recency carries the ranking."""
    signals: list[Signal] = []
    for result in payload.get("results", []):
        url = result.get("url")
        if not url:
            continue
        title = str(result.get("title") or "").strip()
        text = str(result.get("text") or "").strip()
        published = result.get("publishedDate")
        posted_at = to_naive_utc(str(published)) if published else None
        signals.append(
            Signal(
                id=signal_id(str(url)),
                source=source_for(str(url)),
                url=str(url),
                title=title,
                excerpt=excerpt(text or title, EXCERPT_CHARS),
                places_mentioned=extract_places(title, text, destination),
                posted_at=posted_at,
                score=score(posted_at, now),
            )
        )
    return signals


class ExaSource:
    name = "web"

    def __init__(self, client: httpx.Client | None = None, *, now: dt.datetime | None = None) -> None:
        self._client = client if client is not None else httpx.Client(timeout=15.0)
        self._now = now
        self.errors: list[str] = []

    def search(self, brief: TripBrief) -> list[Signal]:
        self.errors = []
        now = self._now if self._now is not None else utc_now()
        try:
            key = self._key()
        except ToolError as error:
            self.errors.append(f"key: {type(error).__name__}")
            return []
        signals: list[Signal] = []
        for term in queries(brief):
            try:
                signals.extend(to_signals(self._search_once(key, term, now), brief.destination, now))
            except (ToolError, httpx.HTTPError) as error:
                self.errors.append(f"search: {type(error).__name__}")
        return best_per_url(signals)

    @staticmethod
    def _key() -> str:
        key = os.environ.get("EXA_API_KEY")
        if not key:
            raise ToolError("EXA_API_KEY is not set")
        return key

    def _search_once(self, key: str, term: str, now: dt.datetime) -> dict[str, Any]:
        response = self._client.post(
            SEARCH_URL,
            headers={"x-api-key": key, "Content-Type": "application/json"},
            json={
                "query": term,
                "numResults": PER_QUERY,
                "startPublishedDate": (now - dt.timedelta(days=LOOKBACK_DAYS)).isoformat(timespec="seconds") + "Z",
                "contents": {"text": {"maxCharacters": TEXT_CHARS}},
            },
        )
        check_status(response, "exa")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ToolError("exa returned a non-object body")
        return payload
