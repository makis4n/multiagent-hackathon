"""Offline. Every YouTube call is replayed from a cassette through respx; nothing opens a socket."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx
import pytest
import respx

from trip_core.models import SignalSource, TripBrief
from trip_research.youtube import SEARCH_URL, VIDEOS_URL, YouTubeSource

NOW = dt.datetime(2026, 9, 13, 12, 0)
CASSETTES = Path(__file__).parent / "cassettes"
SEARCH = json.loads((CASSETTES / "youtube_search.json").read_text())
VIDEOS = json.loads((CASSETTES / "youtube_videos.json").read_text())


def tokyo() -> TripBrief:
    return TripBrief(
        id="tokyo",
        destination="Tokyo",
        origin="ARN",
        start_date=dt.date(2026, 11, 12),
        end_date=dt.date(2026, 11, 16),
        styles=["food", "art"],
    )


@pytest.fixture
def api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")


def mock_both() -> tuple[respx.Route, respx.Route]:
    search = respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=SEARCH))
    videos = respx.get(VIDEOS_URL).mock(return_value=httpx.Response(200, json=VIDEOS))
    return search, videos


@respx.mock
def test_search_returns_signals_from_the_cassette(api_key: None) -> None:
    mock_both()

    signals = YouTubeSource(now=NOW).search(tokyo())

    assert [signal.id for signal in signals] == ["yt-vidAAA", "yt-vidBBB", "yt-vidCCC"]
    assert all(signal.source == SignalSource.youtube for signal in signals)
    assert signals[0].url == "https://www.youtube.com/watch?v=vidAAA"


@respx.mock
def test_a_channel_result_without_a_video_id_is_dropped(api_key: None) -> None:
    mock_both()

    assert all("chanXYZ" not in signal.id for signal in YouTubeSource(now=NOW).search(tokyo()))


@respx.mock
def test_html_entities_in_titles_are_unescaped(api_key: None) -> None:
    mock_both()

    titles = [signal.title for signal in YouTubeSource(now=NOW).search(tokyo())]
    assert "Tsukiji Outer Market food tour & what to skip" in titles
    assert not any("&amp;" in title or "&#39;" in title for title in titles)


@respx.mock
def test_published_at_becomes_naive_utc(api_key: None) -> None:
    """An aware datetime here would raise the moment it met the fixture's naive ones."""
    mock_both()

    signal = YouTubeSource(now=NOW).search(tokyo())[0]
    assert signal.posted_at == dt.datetime(2026, 8, 30, 9, 0)
    assert signal.posted_at is not None and signal.posted_at.tzinfo is None


@respx.mock
def test_places_are_extracted_from_the_video_text(api_key: None) -> None:
    mock_both()

    by_id = {signal.id: signal.places_mentioned for signal in YouTubeSource(now=NOW).search(tokyo())}
    assert "Tsukiji Outer Market" in by_id["yt-vidAAA"]
    assert "teamLab Planets" in by_id["yt-vidBBB"]


@respx.mock
def test_exactly_one_search_call_per_brief(api_key: None) -> None:
    """search.list has its own quota bucket capped at 100 calls a day. One brief must never cost more than one."""
    search, videos = mock_both()

    YouTubeSource(now=NOW).search(tokyo())

    assert search.call_count == 1
    assert videos.call_count == 1


@respx.mock
def test_statistics_are_fetched_for_every_video_in_one_call(api_key: None) -> None:
    _, videos = mock_both()

    YouTubeSource(now=NOW).search(tokyo())

    assert videos.calls.last.request.url.params["id"] == "vidAAA,vidBBB,vidCCC"


@respx.mock
def test_a_hidden_like_count_still_scores(api_key: None) -> None:
    """vidCCC has no likeCount, which is what YouTube returns when an uploader hides likes."""
    mock_both()

    signals = YouTubeSource(now=NOW).search(tokyo())
    stale = next(signal for signal in signals if signal.id == "yt-vidCCC")
    assert 0.0 < stale.score <= 1.0


@respx.mock
def test_a_failed_search_degrades_instead_of_killing_the_loop(api_key: None) -> None:
    """The loop runs research with retries=0 and no try. Raising here would lose the whole trip."""
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(503))

    source = YouTubeSource(now=NOW)
    assert source.search(tokyo()) == []
    assert source.errors == ["search: HTTPError"]


@respx.mock
def test_a_failed_statistics_call_still_returns_the_signals(api_key: None) -> None:
    """Statistics only affect ranking. Losing them must not lose the signals."""
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=SEARCH))
    respx.get(VIDEOS_URL).mock(return_value=httpx.Response(500))

    source = YouTubeSource(now=NOW)
    signals = source.search(tokyo())

    assert len(signals) == 3
    assert source.errors == ["statistics: HTTPError"]


def test_a_missing_api_key_degrades_instead_of_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)

    source = YouTubeSource(now=NOW)
    assert source.search(tokyo()) == []
    assert source.errors == ["search: ToolError"]


@respx.mock
def test_the_api_key_never_appears_in_a_recorded_error(api_key: None) -> None:
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(403))

    source = YouTubeSource(now=NOW)
    source.search(tokyo())
    assert all("test-key" not in error for error in source.errors)
