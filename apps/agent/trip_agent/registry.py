"""Which implementation backs each Protocol. REAL_<NAME>=1 in .env picks the lane's real one; unset picks the fake.

INJECT_BOOKING_FAILURE=1 wraps whichever booking provider is active so its first order call raises after the
provider has created the order, the way a lost response looks. The retry must then find the same order.
"""

from __future__ import annotations

import datetime as dt
import os

import trip_booking
import trip_itinerary
import trip_research
from trip_agent.loop import Tools
from trip_core.fakes import FakeVerifier, default_fakes
from trip_core.models import BookingKind, BookingOption, BookingOrder, RetryableError, TripBrief
from trip_core.tools import BookingProvider

FLAGS = ("RESEARCH", "PLACES", "PLANNER", "VERIFIER", "BOOKING", "CALENDAR")


def real(name: str) -> bool:
    return os.environ.get(f"REAL_{name}", "") == "1"


def active_flags() -> dict[str, bool]:
    return {name: real(name) for name in FLAGS}


def inject_booking_failure() -> bool:
    return os.environ.get("INJECT_BOOKING_FAILURE", "") == "1"


class FailOnce:
    """A BookingProvider whose first order call completes at the provider and then raises RetryableError."""

    def __init__(self, inner: BookingProvider) -> None:
        self.inner = inner
        self.name = inner.name
        self.failed_once = False

    def search(self, brief: TripBrief, kind: BookingKind) -> list[BookingOption]:
        return self.inner.search(brief, kind)

    def order(self, option: BookingOption, idempotency_key: str, confirmed_by_user_at: dt.datetime) -> BookingOrder:
        placed = self.inner.order(option, idempotency_key, confirmed_by_user_at)
        if not self.failed_once:
            self.failed_once = True
            raise RetryableError("injected: provider created the order, then the response was lost")
        return placed


def build_tools() -> Tools:
    fakes = default_fakes()
    resolver = trip_itinerary.build_resolver() if real("PLACES") else fakes.resolver
    booking: BookingProvider = trip_booking.build_provider() if real("BOOKING") else fakes.booking
    if inject_booking_failure():
        booking = FailOnce(booking)
    return Tools(
        research=trip_research.build_sources() if real("RESEARCH") else list(fakes.research),
        resolver=resolver,
        planner=trip_itinerary.build_planner() if real("PLANNER") else fakes.planner,
        verifier=trip_itinerary.build_verifier(resolver) if real("VERIFIER") else FakeVerifier(resolver),
        booking=booking,
        calendar=trip_itinerary.build_calendar() if real("CALENDAR") else fakes.calendar,
    )
