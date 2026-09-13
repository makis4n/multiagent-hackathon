"""Reddit search to Signals over plain httpx.

App-only OAuth: a script app's id and secret exchange for a read token, no user context and no refresh.
httpx rather than PRAW so respx can record every call and CI never touches the network.

search() never raises. The loop runs research with retries=0 and no try (apps/agent/trip_agent/loop.py), so an
exception here would take down the whole trip; a degraded source returns what it has and records why.
"""

from __future__ import annotations

import datetime as dt
import os
from typing import Any

import httpx

from trip_core.models import Signal, SignalSource, ToolError, TripBrief
from trip_research.http import check_status
from trip_research.places import extract_places
from trip_research.rank import best_per_url, excerpt, from_epoch, score, utc_now

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
SEARCH_URL = "https://oauth.reddit.com/search"
EXCERPT_CHARS = 400
PER_QUERY = 25
MAX_QUERIES = 5


def queries(brief: TripBrief) -> list[str]:
    """The destination on its own, then one query per style. Deterministic, so cassettes stay stable."""
    terms = [f"{brief.destination} itinerary", *(f"{brief.destination} {style}" for style in brief.styles)]
    return terms[:MAX_QUERIES]


def to_signals(payload: dict[str, Any], destination: str, now: dt.datetime) -> list[Signal]:
    """Pure. A Reddit listing to Signals."""
    signals: list[Signal] = []
    for child in payload.get("data", {}).get("children", []):
        post = child.get("data", {})
        permalink = post.get("permalink")
        if not permalink or post.get("over_18"):
            continue
        created = post.get("created_utc")
        posted_at = from_epoch(created) if isinstance(created, int | float) else None
        title = str(post.get("title", "")).strip()
        body = str(post.get("selftext", "")).strip()
        signals.append(
            Signal(
                id=f"rd-{post.get('id', '')}",
                source=SignalSource.reddit,
                url=f"https://www.reddit.com{permalink}",
                title=title,
                excerpt=excerpt(body or title, EXCERPT_CHARS),
                places_mentioned=extract_places(title, body, destination),
                posted_at=posted_at,
                score=score(posted_at, now, int(post.get("ups", 0)), int(post.get("num_comments", 0))),
            )
        )
    return signals


class RedditSource:
    name = "reddit"

    def __init__(self, client: httpx.Client | None = None, *, now: dt.datetime | None = None) -> None:
        self._client = client if client is not None else httpx.Client(timeout=10.0)
        self._now = now
        self._token: str | None = None
        self.errors: list[str] = []

    def search(self, brief: TripBrief) -> list[Signal]:
        self.errors = []
        now = self._now if self._now is not None else utc_now()
        try:
            token = self._access_token()
        except (ToolError, httpx.HTTPError) as error:
            self.errors.append(f"token: {type(error).__name__}")
            return []
        signals: list[Signal] = []
        for query in queries(brief):
            try:
                signals.extend(to_signals(self._search_once(token, query), brief.destination, now))
            except (ToolError, httpx.HTTPError) as error:
                self.errors.append(f"search: {type(error).__name__}")
        return best_per_url(signals)

    def _user_agent(self) -> str:
        return os.environ.get("REDDIT_USER_AGENT") or "trip-agent/0.1"

    def _access_token(self) -> str:
        if self._token is not None:
            return self._token
        client_id = os.environ.get("REDDIT_CLIENT_ID")
        client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise ToolError("REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are not set")
        response = self._client.post(
            TOKEN_URL,
            auth=httpx.BasicAuth(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": self._user_agent()},
        )
        check_status(response, "reddit")
        token = response.json().get("access_token")
        if not isinstance(token, str) or not token:
            raise ToolError("reddit returned no access_token")
        self._token = token
        return token

    def _search_once(self, token: str, query: str) -> dict[str, Any]:
        response = self._client.get(
            SEARCH_URL,
            params={"q": query, "sort": "top", "t": "year", "limit": PER_QUERY, "type": "link", "raw_json": 1},
            headers={"Authorization": f"Bearer {token}", "User-Agent": self._user_agent()},
        )
        check_status(response, "reddit")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ToolError("reddit returned a non-object body")
        return payload
