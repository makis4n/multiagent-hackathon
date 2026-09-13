"""Lane C. Draft, refine, resolve, verify, export."""

from trip_core.tools import CalendarSink, ItineraryPlanner, PlaceResolver, Verifier


def build_resolver() -> PlaceResolver:
    """Google Places behind it. Selected by REAL_PLACES=1."""
    raise NotImplementedError("Lane C: implement trip_itinerary.build_resolver()")


def build_planner() -> ItineraryPlanner:
    """Gemini behind it, through trip_core.llm. Selected by REAL_PLANNER=1."""
    raise NotImplementedError("Lane C: implement trip_itinerary.build_planner()")


def build_verifier(resolver: PlaceResolver) -> Verifier:
    """The four checks with Routes API travel times. Selected by REAL_VERIFIER=1."""
    raise NotImplementedError("Lane C: implement trip_itinerary.build_verifier()")


def build_calendar() -> CalendarSink:
    """Google Calendar behind it. Selected by REAL_CALENDAR=1."""
    raise NotImplementedError("Lane C: implement trip_itinerary.build_calendar()")
