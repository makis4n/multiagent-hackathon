"""Offline. Every Exa call is replayed from a cassette through respx; nothing opens a socket."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx
import pytest
import respx

from trip_core.models import SignalSource, TripBrief
from trip_research.web import SEARCH_URL, ExaSource, queries, source_for

NOW = dt.datetime(2026, 9, 13, 12, 0)
CASSETTE = json.loads((Path(__file__).parent / "cassettes" / "exa_search.json").read_text())


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
    monkeypatch.setenv("EXA_API_KEY", "test-key")


def mock_search() -> respx.Route:
    return respx.post(SEARCH_URL).mock(return_value=httpx.Response(200, json=CASSETTE))


@respx.mock
def test_search_returns_signals_from_the_cassette(api_key: None) -> None:
    mock_search()

    signals = ExaSource(now=NOW).search(tokyo())

    assert len(signals) == 3
    assert all(signal.url for signal in signals)


@respx.mock
def test_a_reddit_result_is_labelled_reddit(api_key: None) -> None:
    """Verified live: Exa's includeDomains never actually returns reddit.com, so this path is not exercised
    by any real response today. Kept in case Exa's coverage changes; the cassette exercises it either way."""
    mock_search()

    signals = ExaSource(now=NOW).search(tokyo())
    reddit = [signal for signal in signals if "reddit.com" in signal.url]
    assert reddit and all(signal.source == SignalSource.reddit for signal in reddit)


@respx.mock
def test_a_non_reddit_result_is_labelled_web(api_key: None) -> None:
    mock_search()

    other = next(signal for signal in ExaSource(now=NOW).search(tokyo()) if "timeout.com" in signal.url)
    assert other.source == SignalSource.web


def test_source_for_does_not_match_a_lookalike_domain() -> None:
    assert source_for("https://www.reddit.com/r/Tokyo/x/") == SignalSource.reddit
    assert source_for("https://reddit.com.evil.example/x") == SignalSource.web
    assert source_for("https://notreddit.com/x") == SignalSource.web


@respx.mock
def test_a_result_without_a_url_is_dropped(api_key: None) -> None:
    mock_search()

    assert all(signal.title != "Broken result with no url" for signal in ExaSource(now=NOW).search(tokyo()))


@respx.mock
def test_a_missing_published_date_is_unknown_not_an_error(api_key: None) -> None:
    mock_search()

    other = next(signal for signal in ExaSource(now=NOW).search(tokyo()) if "timeout.com" in signal.url)
    assert other.posted_at is None


@respx.mock
def test_published_dates_are_naive_utc(api_key: None) -> None:
    mock_search()

    dated = [signal for signal in ExaSource(now=NOW).search(tokyo()) if signal.posted_at is not None]
    assert dated and all(signal.posted_at is not None and signal.posted_at.tzinfo is None for signal in dated)


@respx.mock
def test_the_request_has_no_domain_restriction(api_key: None) -> None:
    """Verified live on 2026-09-13: includeDomains=["reddit.com"] returns zero results every time, while the
    same call against a control domain (wikipedia.org, nytimes.com) works normally. Not documented, found by
    direct testing. So this is open web search, not a Reddit channel."""
    route = mock_search()

    ExaSource(now=NOW).search(tokyo())

    body = json.loads(route.calls.last.request.content)
    assert "includeDomains" not in body


@respx.mock
def test_the_key_goes_in_the_x_api_key_header(api_key: None) -> None:
    route = mock_search()

    ExaSource(now=NOW).search(tokyo())

    assert route.calls.last.request.headers["x-api-key"] == "test-key"


@respx.mock
def test_one_request_per_query(api_key: None) -> None:
    route = mock_search()

    ExaSource(now=NOW).search(tokyo())

    assert route.call_count == len(queries(tokyo())) == 2


@respx.mock
def test_one_failed_query_keeps_the_results_of_the_other(api_key: None) -> None:
    respx.post(SEARCH_URL).mock(side_effect=[httpx.Response(500), httpx.Response(200, json=CASSETTE)])

    source = ExaSource(now=NOW)
    signals = source.search(tokyo())

    assert len(signals) == 3
    assert source.errors == ["search: HTTPError"]


@respx.mock
def test_a_dead_endpoint_degrades_instead_of_killing_the_loop(api_key: None) -> None:
    """The loop runs research with retries=0 and no try. Raising here would lose the whole trip."""
    respx.post(SEARCH_URL).mock(return_value=httpx.Response(503))

    source = ExaSource(now=NOW)
    assert source.search(tokyo()) == []
    assert source.errors == ["search: HTTPError", "search: HTTPError"]


def test_a_missing_api_key_degrades_instead_of_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXA_API_KEY", raising=False)

    source = ExaSource(now=NOW)
    assert source.search(tokyo()) == []
    assert source.errors == ["key: ToolError"]
