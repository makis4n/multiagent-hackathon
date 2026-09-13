"""Offline. Every Reddit call is replayed from a cassette through respx; nothing opens a socket."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx
import pytest
import respx

from trip_core.models import SignalSource, TripBrief
from trip_research.reddit import SEARCH_URL, TOKEN_URL, RedditSource, queries

NOW = dt.datetime(2026, 9, 13, 12, 0)
CASSETTE = json.loads((Path(__file__).parent / "cassettes" / "reddit_search.json").read_text())


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
def credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDDIT_CLIENT_ID", "test-id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("REDDIT_USER_AGENT", "trip-agent/0.1 by test")


def mock_token() -> None:
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 3600}))


@respx.mock
def test_search_returns_signals_from_the_cassette(credentials: None) -> None:
    mock_token()
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=CASSETTE))

    signals = RedditSource(now=NOW).search(tokyo())

    assert [signal.id for signal in signals] == ["rd-aa1", "rd-aa2", "rd-aa3"]
    assert all(signal.source == SignalSource.reddit for signal in signals)
    assert signals[0].url == "https://www.reddit.com/r/JapanTravel/comments/aa1/aa1/"
    assert signals[0].posted_at == dt.datetime(2026, 8, 30, 9, 0)


@respx.mock
def test_nsfw_posts_are_dropped(credentials: None) -> None:
    mock_token()
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=CASSETTE))

    assert "rd-aa4" not in [signal.id for signal in RedditSource(now=NOW).search(tokyo())]


@respx.mock
def test_recent_posts_outscore_old_ones(credentials: None) -> None:
    mock_token()
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=CASSETTE))

    signals = RedditSource(now=NOW).search(tokyo())
    by_id = {signal.id: signal.score for signal in signals}
    assert by_id["rd-aa1"] > by_id["rd-aa2"] > by_id["rd-aa3"]
    assert all(0.0 <= score <= 1.0 for score in by_id.values())


@respx.mock
def test_an_empty_body_falls_back_to_the_title(credentials: None) -> None:
    mock_token()
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=CASSETTE))

    old = next(signal for signal in RedditSource(now=NOW).search(tokyo()) if signal.id == "rd-aa3")
    assert old.excerpt == old.title


@respx.mock
def test_the_token_is_fetched_once_for_all_queries(credentials: None) -> None:
    token_route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
    )
    search_route = respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=CASSETTE))

    RedditSource(now=NOW).search(tokyo())

    assert token_route.call_count == 1
    assert search_route.call_count == len(queries(tokyo())) == 3


@respx.mock
def test_a_dead_token_endpoint_degrades_instead_of_killing_the_loop(credentials: None) -> None:
    """The loop runs research with retries=0 and no try. Raising here would lose the whole trip."""
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(503))

    source = RedditSource(now=NOW)
    assert source.search(tokyo()) == []
    assert source.errors == ["token: HTTPError"]


@respx.mock
def test_one_failed_query_keeps_the_results_of_the_others(credentials: None) -> None:
    mock_token()
    responses = [httpx.Response(500), httpx.Response(200, json=CASSETTE), httpx.Response(200, json=CASSETTE)]
    respx.get(SEARCH_URL).mock(side_effect=responses)

    source = RedditSource(now=NOW)
    signals = source.search(tokyo())

    assert len(signals) == 3
    assert source.errors == ["search: HTTPError"]


def test_missing_credentials_degrade_instead_of_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)

    source = RedditSource(now=NOW)
    assert source.search(tokyo()) == []
    assert source.errors == ["token: ToolError"]


def test_queries_are_deterministic_and_capped() -> None:
    brief = tokyo().model_copy(update={"styles": [str(index) for index in range(10)]})
    assert queries(brief) == queries(brief)
    assert len(queries(brief)) == 5
