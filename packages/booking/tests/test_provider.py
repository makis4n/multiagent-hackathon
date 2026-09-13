"""Offline. Every Duffel offer request is replayed from a cassette through respx; nothing opens a socket."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx
import pytest
import respx

from trip_booking.duffel_client import DuffelClient
from trip_booking.provider import DuffelBookingProvider, minor_units
from trip_core.models import BookingKind, RetryableError, ToolError, TripBrief

OFFER_REQUESTS_URL = "https://api.duffel.com/air/offer_requests"
CASSETTES = Path(__file__).parent / "cassettes"
ZZ_CASSETTE = json.loads((CASSETTES / "flights_search_zz.json").read_text())
CASSETTE = json.loads((CASSETTES / "flights_search.json").read_text())


def tokyo() -> TripBrief:
    return TripBrief(
        id="tokyo", destination="HND", origin="ARN", start_date=dt.date(2026, 10, 9), end_date=dt.date(2026, 10, 16)
    )


def provider() -> DuffelBookingProvider:
    return DuffelBookingProvider(DuffelClient("duffel_test_x"))


@respx.mock
def test_zz_sorts_first_even_though_it_is_not_the_cheapest() -> None:
    respx.post(OFFER_REQUESTS_URL).mock(return_value=httpx.Response(201, json=ZZ_CASSETTE))

    options = provider().search(tokyo(), BookingKind.flight)

    offers_by_ref = {offer["id"]: offer for offer in ZZ_CASSETTE["data"]["offers"]}
    top_offer = offers_by_ref[options[0].provider_ref]
    cheapest = min(float(offer["total_amount"]) for offer in ZZ_CASSETTE["data"]["offers"])
    assert top_offer["owner"]["iata_code"] == "ZZ"
    assert float(top_offer["total_amount"]) != cheapest


@respx.mock
def test_the_cheapest_option_is_first_when_there_is_no_zz() -> None:
    respx.post(OFFER_REQUESTS_URL).mock(return_value=httpx.Response(201, json=CASSETTE))

    options = provider().search(tokyo(), BookingKind.flight)

    assert all(offer["owner"]["iata_code"] != "ZZ" for offer in CASSETTE["data"]["offers"])
    assert options[0].price_minor == min(option.price_minor for option in options)


@respx.mock
def test_decimal_amount_becomes_integer_minor_units() -> None:
    respx.post(OFFER_REQUESTS_URL).mock(return_value=httpx.Response(201, json=CASSETTE))

    options = provider().search(tokyo(), BookingKind.flight)

    by_ref = {offer["id"]: offer for offer in CASSETTE["data"]["offers"]}
    for option in options:
        offer = by_ref[option.provider_ref]
        assert option.price_minor == round(float(offer["total_amount"]) * 100)
        assert option.currency == offer["total_currency"]


def test_minor_units_converts_a_decimal_string() -> None:
    assert minor_units("90.80") == 9080
    assert minor_units("100.00") == 10000


def test_minor_units_rejects_a_non_numeric_amount() -> None:
    with pytest.raises(ToolError):
        minor_units("not-a-number")


@respx.mock
def test_results_are_capped_at_five() -> None:
    many_offers = [dict(offer, id=f"off_{index}") for index, offer in enumerate(CASSETTE["data"]["offers"] * 3)]
    payload = json.loads(json.dumps(CASSETTE))
    payload["data"]["offers"] = many_offers
    respx.post(OFFER_REQUESTS_URL).mock(return_value=httpx.Response(201, json=payload))

    options = provider().search(tokyo(), BookingKind.flight)

    assert len(options) == 5


@respx.mock
def test_stays_return_no_options_and_make_no_request() -> None:
    assert provider().search(tokyo(), BookingKind.stay) == []


@respx.mock
def test_activities_return_no_options_and_make_no_request() -> None:
    assert provider().search(tokyo(), BookingKind.activity) == []


@respx.mock
def test_a_500_raises_retryable_error() -> None:
    respx.post(OFFER_REQUESTS_URL).mock(return_value=httpx.Response(500))

    with pytest.raises(RetryableError):
        provider().search(tokyo(), BookingKind.flight)


@respx.mock
def test_a_429_raises_retryable_error() -> None:
    respx.post(OFFER_REQUESTS_URL).mock(return_value=httpx.Response(429))

    with pytest.raises(RetryableError):
        provider().search(tokyo(), BookingKind.flight)


@respx.mock
def test_a_401_raises_tool_error() -> None:
    respx.post(OFFER_REQUESTS_URL).mock(return_value=httpx.Response(401))

    with pytest.raises(ToolError):
        provider().search(tokyo(), BookingKind.flight)


@respx.mock
def test_a_timeout_raises_retryable_error() -> None:
    respx.post(OFFER_REQUESTS_URL).mock(side_effect=httpx.ConnectTimeout("timed out"))

    with pytest.raises(RetryableError):
        provider().search(tokyo(), BookingKind.flight)
