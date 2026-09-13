"""Lane D. Duffel-backed BookingProvider: flight search and the order path behind the confirmation gate.

`order` is safe to call twice under one idempotency key. It looks the key up locally, then in Duffel's own order
list (metadata.idempotency_key), and only then creates. So a retry after a lost response adopts the order the
first call created instead of creating a second one.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from trip_booking.duffel_client import DuffelClient
from trip_core.models import BookingKind, BookingOption, BookingOrder, OrderStatus, ToolError, TripBrief

MAX_OPTIONS = 5
DEFAULT_STORE = Path("logs/orders.json")
TEST_PASSENGERS = [
    {"given_name": "Ada", "family_name": "Traveller", "born_on": "1990-01-01", "gender": "f", "title": "ms"},
    {"given_name": "Bo", "family_name": "Traveller", "born_on": "1991-02-02", "gender": "m", "title": "mr"},
    {"given_name": "Cy", "family_name": "Traveller", "born_on": "1992-03-03", "gender": "m", "title": "mr"},
    {"given_name": "Di", "family_name": "Traveller", "born_on": "1993-04-04", "gender": "f", "title": "ms"},
]


def minor_units(amount: str) -> int:
    """Duffel's decimal string amount ("90.80") to integer minor units (9080)."""
    try:
        return int((Decimal(amount) * 100).to_integral_value())
    except InvalidOperation as error:
        raise ToolError(f"duffel returned a non-numeric amount: {amount!r}") from error


def decimal_amount(minor: int) -> str:
    """Integer minor units (9080) back to Duffel's decimal string ("90.80")."""
    return f"{Decimal(minor) / 100:.2f}"


def _slice_summary(item: dict[str, Any]) -> dict[str, Any]:
    """The part of a Duffel slice a traveller reads before confirming: the legs, their times, cabin and bags."""
    segments = []
    for segment in item.get("segments", []):
        passenger = (segment.get("passengers") or [{}])[0]
        bags = {bag.get("type"): bag.get("quantity", 0) for bag in passenger.get("baggages") or []}
        segments.append(
            {
                "origin": segment.get("origin", {}).get("iata_code", ""),
                "destination": segment.get("destination", {}).get("iata_code", ""),
                "departing_at": segment.get("departing_at", ""),
                "arriving_at": segment.get("arriving_at", ""),
                "duration": segment.get("duration", ""),
                "carrier": segment.get("marketing_carrier", {}).get("name", ""),
                "flight_number": f"{segment.get('marketing_carrier', {}).get('iata_code', '')}"
                f"{segment.get('marketing_carrier_flight_number', '')}",
                "cabin": passenger.get("cabin_class_marketing_name") or passenger.get("cabin_class") or "",
                "checked_bags": bags.get("checked", 0),
                "carry_on_bags": bags.get("carry_on", 0),
            }
        )
    return {
        "origin": item.get("origin", {}).get("iata_code", ""),
        "destination": item.get("destination", {}).get("iata_code", ""),
        "duration": item.get("duration", ""),
        "fare_brand": item.get("fare_brand_name") or "",
        "segments": segments,
    }


def _order_key(offer: dict[str, Any]) -> int:
    """ZZ (Duffel's own sandbox airline) sorts first regardless of price."""
    return 0 if offer.get("owner", {}).get("iata_code") == "ZZ" else 1


class OrderStore:
    """Orders by idempotency key, in memory and in one JSON file so a second process finds them too."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.orders: dict[str, BookingOrder] = {}
        if path is not None and path.exists():
            for key, data in json.loads(path.read_text()).items():
                self.orders[key] = BookingOrder.model_validate(data)

    def get(self, key: str) -> BookingOrder | None:
        return self.orders.get(key)

    def put(self, order: BookingOrder) -> None:
        self.orders[order.idempotency_key] = order
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({key: value.model_dump(mode="json") for key, value in self.orders.items()}, indent=2)
            )

    def __len__(self) -> int:
        return len(self.orders)


class DuffelBookingProvider:
    """Lane D. `name`, `search` and `order` per the BookingProvider Protocol in trip_core.tools."""

    name = "duffel"

    def __init__(self, client: DuffelClient, store: OrderStore | None = None) -> None:
        self._client = client
        self.store = store if store is not None else OrderStore()

    def search(self, brief: TripBrief, kind: BookingKind) -> list[BookingOption]:
        if kind == BookingKind.flight:
            return self._search_flights(brief)
        if kind == BookingKind.stay:
            return []  # Duffel Stays requires a commercial agreement; unavailable on the test account
        return []  # activities: no provider wired up yet

    def _search_flights(self, brief: TripBrief) -> list[BookingOption]:
        origin, destination = brief.airports
        body = {
            "data": {
                "passengers": [{"type": "adult"} for _ in range(brief.travellers)],
                "slices": [
                    {"origin": origin, "destination": destination, "departure_date": brief.start_date.isoformat()},
                    {"origin": destination, "destination": origin, "departure_date": brief.end_date.isoformat()},
                ],
            }
        }
        payload = self._client.create_offer_request(body)
        offers = payload.get("data", {}).get("offers", [])
        ordered = sorted(offers, key=lambda offer: minor_units(offer["total_amount"]))
        ordered = sorted(ordered, key=_order_key)
        return [self._to_option(brief, offer) for offer in ordered[:MAX_OPTIONS]]

    def _to_option(self, brief: TripBrief, offer: dict[str, Any]) -> BookingOption:
        origin, destination = brief.airports
        owner_name = offer.get("owner", {}).get("name", "Unknown airline")
        passenger_ids = [passenger["id"] for passenger in offer.get("passengers", []) if "id" in passenger]
        return BookingOption(
            kind=BookingKind.flight,
            provider=self.name,
            provider_ref=offer["id"],
            title=f"{owner_name}, {origin} to {destination}, return, {brief.travellers} pax",
            price_minor=minor_units(offer["total_amount"]),
            currency=offer["total_currency"],
            details={
                "depart": brief.start_date.isoformat(),
                "return": brief.end_date.isoformat(),
                "passenger_ids": passenger_ids,
                "brief_id": brief.id,
                "airline": owner_name,
                "slices": [_slice_summary(item) for item in offer.get("slices", [])],
            },
        )

    def order(self, option: BookingOption, idempotency_key: str, confirmed_by_user_at: dt.datetime) -> BookingOrder:
        if confirmed_by_user_at is None:  # a runtime guard for callers that ignore the type
            raise ToolError("refusing an order without confirmed_by_user_at")
        existing = self.store.get(idempotency_key)
        if existing is not None:
            return existing
        data = self._find_at_provider(idempotency_key)
        if data is None:
            data = self._client.create_order(self._order_body(option, idempotency_key)).get("data") or {}
        order = self._to_order(option, idempotency_key, confirmed_by_user_at, data)
        self.store.put(order)
        return order

    def _find_at_provider(self, idempotency_key: str) -> dict[str, Any] | None:
        """The order this key already created, when its response never reached us."""
        for order in self._client.list_orders():
            metadata = order.get("metadata") or {}
            if metadata.get("idempotency_key") == idempotency_key:
                return order
        return None

    def _order_body(self, option: BookingOption, idempotency_key: str) -> dict[str, Any]:
        passenger_ids = option.details.get("passenger_ids") or []
        if not passenger_ids:
            raise ToolError("option carries no passenger ids; search again before ordering")
        passengers = [
            {
                "id": passenger_id,
                **TEST_PASSENGERS[index % len(TEST_PASSENGERS)],
                "email": f"traveller{index + 1}@example.com",
                "phone_number": f"+4670000000{index + 1}",
            }
            for index, passenger_id in enumerate(passenger_ids)
        ]
        return {
            "data": {
                "selected_offers": [option.provider_ref],
                "passengers": passengers,
                "payments": [
                    {"type": "balance", "amount": decimal_amount(option.price_minor), "currency": option.currency}
                ],
                "metadata": {"idempotency_key": idempotency_key, "brief_id": str(option.details.get("brief_id", ""))},
            }
        }

    def _to_order(
        self, option: BookingOption, idempotency_key: str, confirmed_by_user_at: dt.datetime, data: dict[str, Any]
    ) -> BookingOrder:
        if "id" not in data:
            raise ToolError("duffel order response carries no id")
        total = data.get("total_amount")
        return BookingOrder(
            id=f"ord_{uuid.uuid5(uuid.NAMESPACE_URL, idempotency_key).hex[:10]}",
            option=option,
            idempotency_key=idempotency_key,
            confirmed_by_user_at=confirmed_by_user_at,
            status=OrderStatus.confirmed,
            provider_order_id=data.get("booking_reference") or data["id"],
            receipt={
                "duffel_order_id": data["id"],
                "total_minor": minor_units(str(total)) if total is not None else option.price_minor,
                "currency": data.get("total_currency", option.currency),
            },
        )
