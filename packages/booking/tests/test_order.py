"""Offline. The order path: the confirmation gate, the idempotency key, and the lost-response recovery (D4).
Every Duffel call is replayed through respx; nothing opens a socket. respx.calls counts what the provider sent."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx
import pytest
import respx

from trip_booking.duffel_client import DuffelClient
from trip_booking.provider import DuffelBookingProvider, OrderStore, decimal_amount
from trip_core.models import BookingKind, RetryableError, ToolError, TripBrief, idempotency_key

OFFER_REQUESTS_URL = "https://api.duffel.com/air/offer_requests"
ORDERS_URL = "https://api.duffel.com/air/orders"
CASSETTES = Path(__file__).parent / "cassettes"
SEARCH = json.loads((CASSETTES / "flights_search.json").read_text())
CREATE = json.loads((CASSETTES / "order_create.json").read_text())
LIST = json.loads((CASSETTES / "orders_list.json").read_text())
EMPTY_LIST = {"meta": {"after": None, "before": None, "limit": 50}, "data": []}
NOW = dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC)


def tokyo() -> TripBrief:
    return TripBrief(
        id="tokyo", destination="HND", origin="ARN", start_date=dt.date(2026, 10, 9), end_date=dt.date(2026, 10, 16)
    )


def provider(store: OrderStore | None = None) -> DuffelBookingProvider:
    return DuffelBookingProvider(DuffelClient("duffel_test_x"), store)


def with_key(payload: dict, key: str) -> dict:
    """The cassettes carry a placeholder key; the test stamps the key it is about to use."""
    text = json.dumps(payload).replace("REPLACED_BY_TEST", key)
    return json.loads(text)


def searched(booking: DuffelBookingProvider):
    respx.post(OFFER_REQUESTS_URL).mock(return_value=httpx.Response(201, json=SEARCH))
    option = booking.search(tokyo(), BookingKind.flight)[0]
    return option, idempotency_key("tokyo", option)


@respx.mock
def test_search_keeps_the_offer_passenger_ids_for_the_order() -> None:
    option, _ = searched(provider())
    offer = next(offer for offer in SEARCH["data"]["offers"] if offer["id"] == option.provider_ref)
    assert option.details["passenger_ids"] == [passenger["id"] for passenger in offer["passengers"]]


@respx.mock
def test_order_refuses_unconfirmed() -> None:
    booking = provider()
    option, key = searched(booking)
    orders = respx.route(url__startswith=ORDERS_URL).mock(return_value=httpx.Response(500))

    with pytest.raises(ToolError):
        booking.order(option, key, None)  # type: ignore[arg-type]

    assert orders.call_count == 0
    assert len(booking.store) == 0


@respx.mock
def test_order_creates_once_and_returns_the_booking_reference() -> None:
    booking = provider()
    option, key = searched(booking)
    listing = respx.get(ORDERS_URL).mock(return_value=httpx.Response(200, json=EMPTY_LIST))
    create = respx.post(ORDERS_URL).mock(return_value=httpx.Response(201, json=with_key(CREATE, key)))

    order = booking.order(option, key, NOW)

    assert order.provider_order_id == "ZZ7K4Q"
    assert order.receipt["duffel_order_id"] == CREATE["data"]["id"]
    assert order.receipt["total_minor"] == 97728
    assert listing.call_count == 1 and create.call_count == 1
    sent = json.loads(create.calls[0].request.content)["data"]
    assert sent["selected_offers"] == [option.provider_ref]
    assert sent["metadata"]["idempotency_key"] == key
    assert [passenger["id"] for passenger in sent["passengers"]] == option.details["passenger_ids"]
    assert all(passenger["email"] and passenger["born_on"] for passenger in sent["passengers"])
    assert sent["payments"] == [{"type": "balance", "amount": decimal_amount(option.price_minor), "currency": "EUR"}]


@respx.mock
def test_order_is_idempotent() -> None:
    booking = provider()
    option, key = searched(booking)
    respx.get(ORDERS_URL).mock(return_value=httpx.Response(200, json=EMPTY_LIST))
    create = respx.post(ORDERS_URL).mock(return_value=httpx.Response(201, json=with_key(CREATE, key)))

    first = booking.order(option, key, NOW)
    second = booking.order(option, key, NOW)

    assert first.id == second.id
    assert first.provider_order_id == second.provider_order_id
    assert create.call_count == 1
    assert len(booking.store) == 1


@respx.mock
def test_lost_create_response_recovers_from_the_provider(tmp_path: Path) -> None:
    """D4. Duffel created the order, the response never arrived, the retry under the same key adopts it."""
    booking = provider(OrderStore(tmp_path / "orders.json"))
    option, key = searched(booking)
    create = respx.post(ORDERS_URL).mock(side_effect=httpx.ReadTimeout("response lost"))
    listing = respx.get(ORDERS_URL).mock(
        side_effect=[httpx.Response(200, json=EMPTY_LIST), httpx.Response(200, json=with_key(LIST, key))]
    )

    with pytest.raises(RetryableError):
        booking.order(option, key, NOW)
    assert len(booking.store) == 0

    recovered = booking.order(option, key, NOW)

    assert create.call_count == 1
    assert listing.call_count == 2
    assert recovered.provider_order_id == "ZZ7K4Q"
    assert recovered.receipt["duffel_order_id"] == LIST["data"][0]["id"]
    assert len(booking.store) == 1


@respx.mock
def test_the_store_survives_a_new_process(tmp_path: Path) -> None:
    path = tmp_path / "orders.json"
    booking = provider(OrderStore(path))
    option, key = searched(booking)
    respx.get(ORDERS_URL).mock(return_value=httpx.Response(200, json=EMPTY_LIST))
    create = respx.post(ORDERS_URL).mock(return_value=httpx.Response(201, json=with_key(CREATE, key)))
    first = booking.order(option, key, NOW)

    again = provider(OrderStore(path)).order(option, key, NOW)

    assert again == first
    assert create.call_count == 1


@respx.mock
def test_an_expired_offer_says_search_again() -> None:
    booking = provider()
    option, key = searched(booking)
    respx.get(ORDERS_URL).mock(return_value=httpx.Response(200, json=EMPTY_LIST))
    body = {"errors": [{"code": "offer_no_longer_available", "message": "not shown", "title": "x"}]}
    respx.post(ORDERS_URL).mock(return_value=httpx.Response(422, json=body))

    with pytest.raises(ToolError, match="offer expired"):
        booking.order(option, key, NOW)
    assert len(booking.store) == 0


@respx.mock
def test_insufficient_balance_says_so() -> None:
    booking = provider()
    option, key = searched(booking)
    respx.get(ORDERS_URL).mock(return_value=httpx.Response(200, json=EMPTY_LIST))
    body = {"errors": [{"code": "insufficient_balance", "message": "not shown"}]}
    respx.post(ORDERS_URL).mock(return_value=httpx.Response(422, json=body))

    with pytest.raises(ToolError, match="insufficient balance"):
        booking.order(option, key, NOW)


@respx.mock
def test_a_502_on_create_is_retryable() -> None:
    booking = provider()
    option, key = searched(booking)
    respx.get(ORDERS_URL).mock(return_value=httpx.Response(200, json=EMPTY_LIST))
    respx.post(ORDERS_URL).mock(return_value=httpx.Response(502))

    with pytest.raises(RetryableError):
        booking.order(option, key, NOW)
