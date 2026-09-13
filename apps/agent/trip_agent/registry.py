"""Which implementation backs each Protocol. REAL_<NAME>=1 in .env picks the lane's real one; unset picks the fake."""

from __future__ import annotations

import os

import trip_booking
import trip_itinerary
import trip_research
from trip_agent.loop import Tools
from trip_core.fakes import FakeVerifier, default_fakes

FLAGS = ("RESEARCH", "PLACES", "PLANNER", "VERIFIER", "BOOKING", "CALENDAR")


def real(name: str) -> bool:
    return os.environ.get(f"REAL_{name}", "") == "1"


def active_flags() -> dict[str, bool]:
    return {name: real(name) for name in FLAGS}


def build_tools() -> Tools:
    fakes = default_fakes()
    resolver = trip_itinerary.build_resolver() if real("PLACES") else fakes.resolver
    return Tools(
        research=trip_research.build_sources() if real("RESEARCH") else list(fakes.research),
        resolver=resolver,
        planner=trip_itinerary.build_planner() if real("PLANNER") else fakes.planner,
        verifier=trip_itinerary.build_verifier(resolver) if real("VERIFIER") else FakeVerifier(resolver),
        booking=trip_booking.build_provider() if real("BOOKING") else fakes.booking,
        calendar=trip_itinerary.build_calendar() if real("CALENDAR") else fakes.calendar,
    )
