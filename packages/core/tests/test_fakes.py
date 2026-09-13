import datetime as dt

import pytest

from trip_core.fakes import FakeBooking, FakePlaceResolver, FakePlanner, FakeResearch, FakeVerifier
from trip_core.models import BookingKind, RetryableError, ToolError, TripBrief, idempotency_key, load_fixture
from trip_core.tools import resolve_places

NOW = dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC)


def lisbon() -> TripBrief:
    return TripBrief(
        id="lisbon", destination="Lisbon", origin="ARN", start_date=dt.date(2026, 10, 9), end_date=dt.date(2026, 10, 12)
    )


def test_order_is_idempotent() -> None:
    booking = FakeBooking()
    option = booking.search(lisbon(), BookingKind.flight)[0]
    key = idempotency_key("lisbon", option)
    first = booking.order(option, key, NOW)
    second = booking.order(option, key, NOW)
    assert first.id == second.id
    assert len(booking.orders) == 1


def test_order_refuses_unconfirmed() -> None:
    booking = FakeBooking()
    option = booking.search(lisbon(), BookingKind.stay)[0]
    with pytest.raises(ToolError):
        booking.order(option, "key", None)  # type: ignore[arg-type]
    assert booking.orders == {}


def test_fail_once_recovers_without_a_duplicate() -> None:
    booking = FakeBooking()
    option = booking.search(lisbon(), BookingKind.flight)[0]
    key = idempotency_key("lisbon", option)
    booking.fail_once.add(key)
    with pytest.raises(RetryableError):
        booking.order(option, key, NOW)
    recovered = booking.order(option, key, NOW)
    assert len(booking.orders) == 1
    assert recovered.provider_order_id == booking.orders[key].provider_order_id


def test_verifier_flags_the_closed_venue() -> None:
    fixture = load_fixture("tokyo")
    signals = FakeResearch(fixture.signals, "Tokyo").search(fixture.brief)
    itinerary = FakePlanner().draft(fixture.brief, signals)
    resolver = FakePlaceResolver()
    resolved, places = resolve_places(itinerary, resolver, "Tokyo")
    report = FakeVerifier(resolver).verify(resolved)
    assert report.failed_stop_ids() == ["stop-closed"]
    assert len(places) == len({stop.place_name for stop in resolved.stops()})


def test_fake_research_covers_a_generic_destination() -> None:
    signals = FakeResearch().search(lisbon())
    assert len(signals) == 16
    assert len({place for signal in signals for place in signal.places_mentioned}) >= 10
    assert len({signal.url for signal in signals}) == 16
