from __future__ import annotations

import datetime as dt

from trip_core.models import Signal, SignalSource
from trip_research.rank import best_per_url, excerpt, from_epoch, popularity_weight, recency_weight, score

NOW = dt.datetime(2026, 9, 13, 12, 0)


def test_recency_halves_at_the_half_life() -> None:
    assert recency_weight(NOW, NOW) == 1.0
    assert recency_weight(NOW - dt.timedelta(days=120), NOW) == 0.5
    assert round(recency_weight(NOW - dt.timedelta(days=90), NOW), 2) == 0.59


def test_ninety_days_beats_a_year_ago() -> None:
    recent = recency_weight(NOW - dt.timedelta(days=89), NOW)
    stale = recency_weight(NOW - dt.timedelta(days=365), NOW)
    assert recent > stale


def test_an_unknown_date_scores_below_anything_recent() -> None:
    assert recency_weight(None, NOW) < recency_weight(NOW - dt.timedelta(days=180), NOW)


def test_popularity_saturates() -> None:
    assert popularity_weight(0, 0) == 0.0
    assert popularity_weight(10_000_000, 0) == 1.0
    assert popularity_weight(100, 0) < popularity_weight(1000, 0)


def test_score_stays_in_range() -> None:
    assert score(NOW, NOW, 10_000_000, 10_000_000) <= 1.0
    assert score(None, NOW, 0, 0) >= 0.0


def test_a_future_timestamp_does_not_exceed_one() -> None:
    assert recency_weight(NOW + dt.timedelta(days=30), NOW) == 1.0


def test_from_epoch_is_naive_utc() -> None:
    """The tokyo fixture stores naive datetimes; an aware one here would raise on subtraction."""
    moment = from_epoch(dt.datetime(2026, 8, 30, 9, 0, tzinfo=dt.UTC).timestamp())
    assert moment.tzinfo is None
    assert moment == dt.datetime(2026, 8, 30, 9, 0)


def test_excerpt_cuts_on_a_word_boundary() -> None:
    assert excerpt("  a   b\n\nc  ", 80) == "a b c"
    assert excerpt("alpha beta gamma", 11) == "alpha..."


def test_excerpt_never_exceeds_its_limit() -> None:
    text = "alpha beta gamma delta epsilon zeta eta theta"
    assert all(len(excerpt(text, limit)) <= limit for limit in range(1, len(text) + 5))


def signal(signal_id: str, url: str, score_value: float) -> Signal:
    return Signal(id=signal_id, source=SignalSource.reddit, url=url, title="t", excerpt="e", score=score_value)


def test_best_per_url_keeps_the_best_and_sorts() -> None:
    kept = best_per_url([signal("a", "u1", 0.2), signal("b", "u1", 0.9), signal("c", "u2", 0.5)])
    assert [item.id for item in kept] == ["b", "c"]
