"""YouTube Data API v3 to Signals over plain httpx.

Two calls per brief: one search.list for the video ids, then one batched videos.list for their statistics.
search.list is capped at 100 calls per day against its own quota bucket, so this issues exactly one per brief;
videos.list costs 1 unit and takes every id at once, which is why the statistics are worth fetching at all.

search() never raises. The loop runs research with retries=0 and no try (apps/agent/trip_agent/loop.py).
"""

from __future__ import annotations

import datetime as dt
import html
import os
from typing import Any

import httpx

from trip_core.models import Signal, SignalSource, ToolError, TripBrief
from trip_research.extract_llm import refine_places
from trip_research.http import check_status
from trip_research.places import extract_places
from trip_research.rank import best_per_url, excerpt, score, to_naive_utc, utc_now

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
EXCERPT_CHARS = 400
MAX_RESULTS = 50
LOOKBACK_DAYS = 730
VIEWS_PER_UPVOTE = 100


def query(brief: TripBrief) -> str:
    """One query per brief, because search.list burns one of only 100 daily calls."""
    styles = " ".join(brief.styles[:2])
    return f"{brief.destination} {styles} travel guide".replace("  ", " ").strip()


def _count(statistics: dict[str, Any], field: str) -> int:
    """YouTube returns counts as strings, and omits likeCount entirely when the uploader hides it."""
    raw = statistics.get(field)
    if raw is None:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def popularity(statistics: dict[str, Any]) -> tuple[int, int]:
    """Likes read like upvotes. With likes hidden, views stand in at a hundred to one."""
    likes = _count(statistics, "likeCount")
    views = _count(statistics, "viewCount")
    return (likes or views // VIEWS_PER_UPVOTE), _count(statistics, "commentCount")


def to_signals(
    items: list[dict[str, Any]], statistics: dict[str, dict[str, Any]], destination: str, now: dt.datetime
) -> list[Signal]:
    """Pure. search.list items plus the statistics looked up by video id."""
    signals: list[Signal] = []
    for item in items:
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        snippet = item.get("snippet", {})
        title = html.unescape(str(snippet.get("title", "")).strip())
        description = html.unescape(str(snippet.get("description", "")).strip())
        posted_at = to_naive_utc(str(snippet.get("publishedAt", "")))
        upvotes, comments = popularity(statistics.get(video_id, {}))
        signals.append(
            Signal(
                id=f"yt-{video_id}",
                source=SignalSource.youtube,
                url=f"https://www.youtube.com/watch?v={video_id}",
                title=title,
                excerpt=excerpt(description or title, EXCERPT_CHARS),
                places_mentioned=extract_places(title, description, destination),
                posted_at=posted_at,
                score=score(posted_at, now, upvotes, comments),
            )
        )
    return signals


class YouTubeSource:
    name = "youtube"

    def __init__(self, client: httpx.Client | None = None, *, now: dt.datetime | None = None) -> None:
        self._client = client if client is not None else httpx.Client(timeout=10.0)
        self._now = now
        self.errors: list[str] = []

    def search(self, brief: TripBrief) -> list[Signal]:
        self.errors = []
        now = self._now if self._now is not None else utc_now()
        try:
            key = self._key()
            items = self._search_once(key, query(brief), now)
        except (ToolError, httpx.HTTPError) as error:
            self.errors.append(f"search: {type(error).__name__}")
            return []
        video_ids = [item["id"]["videoId"] for item in items if item.get("id", {}).get("videoId")]
        statistics: dict[str, dict[str, Any]] = {}
        if video_ids:
            try:
                statistics = self._statistics(key, video_ids)
            except (ToolError, httpx.HTTPError) as error:
                self.errors.append(f"statistics: {type(error).__name__}")
        signals = refine_places(to_signals(items, statistics, brief.destination, now), brief.destination)
        return best_per_url(signals)

    @staticmethod
    def _key() -> str:
        key = os.environ.get("YOUTUBE_API_KEY")
        if not key:
            raise ToolError("YOUTUBE_API_KEY is not set")
        return key

    def _search_once(self, key: str, term: str, now: dt.datetime) -> list[dict[str, Any]]:
        published_after = (now - dt.timedelta(days=LOOKBACK_DAYS)).isoformat(timespec="seconds") + "Z"
        response = self._client.get(
            SEARCH_URL,
            params={
                "part": "snippet",
                "q": term,
                "type": "video",
                "order": "relevance",
                "maxResults": MAX_RESULTS,
                "publishedAfter": published_after,
                "key": key,
            },
        )
        check_status(response, "youtube")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ToolError("youtube returned a non-object body")
        items = payload.get("items", [])
        return items if isinstance(items, list) else []

    def _statistics(self, key: str, video_ids: list[str]) -> dict[str, dict[str, Any]]:
        response = self._client.get(VIDEOS_URL, params={"part": "statistics", "id": ",".join(video_ids), "key": key})
        check_status(response, "youtube")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ToolError("youtube returned a non-object body")
        return {
            item["id"]: item.get("statistics", {})
            for item in payload.get("items", [])
            if isinstance(item, dict) and item.get("id")
        }
