"""Lane C. Draft, refine, resolve, verify, export."""

import os

from trip_core.models import ToolError
from trip_core.tools import CalendarSink, ItineraryPlanner, PlaceResolver, Verifier


def maps_key() -> str:
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        raise ToolError("GOOGLE_MAPS_API_KEY is not set; Places API (New) and Routes API must be enabled on it")
    return key


def build_resolver() -> PlaceResolver:
    """Google Places behind it. Selected by REAL_PLACES=1."""
    from trip_itinerary.places import GooglePlaces

    return GooglePlaces(maps_key())


def build_planner() -> ItineraryPlanner:
    """Gemini behind it, through trip_core.llm. Selected by REAL_PLANNER=1."""
    from trip_itinerary.planner import GeminiPlanner

    return GeminiPlanner()


def build_verifier(resolver: PlaceResolver) -> Verifier:
    """The four checks with Routes API travel times. Selected by REAL_VERIFIER=1."""
    from trip_itinerary.verifier import RoutesTravel, RoutesVerifier

    return RoutesVerifier(resolver, RoutesTravel(maps_key()))


def build_calendar() -> CalendarSink:
    """Google Calendar behind it. Selected by REAL_CALENDAR=1."""
    raise NotImplementedError("Lane C: implement trip_itinerary.build_calendar()")
