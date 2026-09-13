"""Lane C. Draft, refine, resolve, verify, export."""

from __future__ import annotations

import logging

from trip_core.fakes import FakePlanner
from trip_core.models import Itinerary, Signal, TripBrief
from trip_core.tools import CalendarSink, ItineraryPlanner, PlaceResolver, Verifier
from trip_itinerary.planner import GeminiPlanner

logging.getLogger(__name__).addHandler(logging.NullHandler())


class PlannerWithFakeDraft(GeminiPlanner):
    """A part-real planner: `questions`, `refine` and `replace_failed` call Gemini, `draft` does not.

    `draft` delegates to `trip_core.fakes.FakePlanner`. A plan this returns is a fake draft that a real model
    then refines, and it must never be read as a real draft. The real draft gets its own spec.
    """

    def __init__(self, *, temperature: float = 0.3) -> None:
        super().__init__(temperature=temperature)
        self.fake_draft = FakePlanner()

    def draft(self, brief: TripBrief, signals: list[Signal]) -> Itinerary:
        """Not model-backed. Hands straight to `trip_core.fakes.FakePlanner.draft`."""
        return self.fake_draft.draft(brief, signals)


def build_resolver() -> PlaceResolver:
    """Google Places behind it. Selected by REAL_PLACES=1."""
    raise NotImplementedError("Lane C: implement trip_itinerary.build_resolver()")


def build_planner() -> ItineraryPlanner:
    """Gemini behind it, through trip_core.llm. Selected by REAL_PLANNER=1.

    `draft` is the fake one until it is specced; everything else is the model. See the README table.
    """
    return PlannerWithFakeDraft()


def build_verifier(resolver: PlaceResolver) -> Verifier:
    """The four checks with Routes API travel times. Selected by REAL_VERIFIER=1."""
    raise NotImplementedError("Lane C: implement trip_itinerary.build_verifier()")


def build_calendar() -> CalendarSink:
    """Google Calendar behind it. Selected by REAL_CALENDAR=1."""
    raise NotImplementedError("Lane C: implement trip_itinerary.build_calendar()")
