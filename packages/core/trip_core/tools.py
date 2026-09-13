"""The Protocols. Each lane implements one; the loop calls them; every one has a fake in trip_core.fakes."""

from __future__ import annotations

import datetime as dt
from typing import Protocol

from trip_core.models import (
    BookingKind,
    BookingOption,
    BookingOrder,
    Itinerary,
    ItineraryPatch,
    Place,
    Signal,
    TripBrief,
    VerificationReport,
)


class ResearchSource(Protocol):
    """Lane B. One per source: reddit, youtube, web."""

    name: str

    def search(self, brief: TripBrief) -> list[Signal]: ...


class PlaceResolver(Protocol):
    """Lane C. Google Places behind it. `get` must return what `resolve` returned for that id."""

    def resolve(self, name: str, near: str) -> Place | None: ...

    def get(self, place_id: str) -> Place | None: ...


class ItineraryPlanner(Protocol):
    """Lane C. The model-backed steps. Each returns typed data; the loop applies the patches."""

    def draft(self, brief: TripBrief, signals: list[Signal]) -> Itinerary: ...

    def questions(self, brief: TripBrief, itinerary: Itinerary) -> list[str]: ...

    def refine(
        self, brief: TripBrief, itinerary: Itinerary, answers: dict[str, str], signals: list[Signal]
    ) -> list[ItineraryPatch]: ...

    def replace_failed(
        self, brief: TripBrief, itinerary: Itinerary, report: VerificationReport, signals: list[Signal]
    ) -> list[ItineraryPatch]: ...


class Verifier(Protocol):
    """Lane C. Deterministic checks: exists, open, reachable, in_window. Never a model."""

    def verify(self, itinerary: Itinerary) -> VerificationReport: ...


class BookingProvider(Protocol):
    """Lane D. Duffel behind it. `order` looks the idempotency key up before creating anything."""

    name: str

    def search(self, brief: TripBrief, kind: BookingKind) -> list[BookingOption]: ...

    def order(self, option: BookingOption, idempotency_key: str, confirmed_by_user_at: dt.datetime) -> BookingOrder: ...


class CalendarSink(Protocol):
    """Lane C. Google Calendar behind it. Returns the URL of what it wrote."""

    def export(self, itinerary: Itinerary, brief: TripBrief) -> str: ...


def resolve_places(itinerary: Itinerary, resolver: PlaceResolver, near: str) -> tuple[Itinerary, dict[str, Place]]:
    """Pure. Sets place_id on every stop the resolver knows; leaves None on the rest so `exists` fails loudly."""
    result = itinerary.model_copy(deep=True)
    places: dict[str, Place] = {}
    for stop in result.stops():
        place = resolver.get(stop.place_id) if stop.place_id else resolver.resolve(stop.place_name, near)
        if place is None:
            stop.place_id = None
            continue
        stop.place_id = place.id
        places[place.id] = place
    return result, places
