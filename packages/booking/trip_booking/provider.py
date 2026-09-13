"""Lane D. Duffel-backed BookingProvider. search() works; order() ships in a follow-up PR (D2 -> D3)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import Any

from trip_booking.duffel_client import DuffelClient
from trip_core.models import BookingKind, BookingOption, BookingOrder, ToolError, TripBrief

MAX_OPTIONS = 5


def minor_units(amount: str) -> int:
    """Duffel's decimal string amount ("90.80") to integer minor units (9080)."""
    try:
        return int((Decimal(amount) * 100).to_integral_value())
    except InvalidOperation as error:
        raise ToolError(f"duffel returned a non-numeric amount: {amount!r}") from error


def _order_key(offer: dict[str, Any]) -> int:
    """ZZ (Duffel's own sandbox airline) sorts first regardless of price."""
    return 0 if offer.get("owner", {}).get("iata_code") == "ZZ" else 1


class DuffelBookingProvider:
    """Lane D. `name` and `search` per the BookingProvider Protocol in trip_core.tools."""

    name = "duffel"

    def __init__(self, client: DuffelClient) -> None:
        self._client = client

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
        return BookingOption(
            kind=BookingKind.flight,
            provider=self.name,
            provider_ref=offer["id"],
            title=f"{owner_name}, {origin} to {destination}, return, {brief.travellers} pax",
            price_minor=minor_units(offer["total_amount"]),
            currency=offer["total_currency"],
            details={"depart": brief.start_date.isoformat(), "return": brief.end_date.isoformat()},
        )

    def order(self, option: BookingOption, idempotency_key: str, confirmed_by_user_at: dt.datetime) -> BookingOrder:
        raise NotImplementedError("D2")
