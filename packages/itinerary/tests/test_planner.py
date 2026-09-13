"""The draft, recorded once (RECORD=1 with a model key in the environment), replayed offline."""

import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from trip_core import llm
from trip_core.cassette import cassette
from trip_core.llm import complete_json
from trip_core.models import TripBrief, load_fixture
from trip_itinerary.draft import DraftItinerary, DraftStop, parse_time, to_itinerary
from trip_itinerary.planner import GeminiPlanner

CASSETTES = Path(__file__).parent / "cassettes"


def recorded(name: str):
    def complete(prompt: str, schema: type[BaseModel], **kwargs: Any) -> BaseModel:
        data = cassette(
            CASSETTES / f"{name}_{schema.__name__}.json", lambda: complete_json(prompt, schema, **kwargs).model_dump()
        )
        return schema.model_validate(data)

    return complete


def test_tokyo_draft_has_a_full_day_plan_from_the_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = load_fixture("tokyo")
    monkeypatch.setattr(llm, "complete_json", recorded("tokyo"))
    itinerary = GeminiPlanner().draft(fixture.brief, fixture.signals)
    assert [day.date for day in itinerary.days] == fixture.brief.dates
    assert all(len(day.stops) >= 2 for day in itinerary.days)
    known = {signal.id for signal in fixture.signals}
    places = [stop.place_name for stop in itinerary.stops()]
    assert len(places) == len(set(places))
    assert all(stop.signal_ids and set(stop.signal_ids) <= known for stop in itinerary.stops())
    assert all(stop.start < stop.end for stop in itinerary.stops())


def test_to_itinerary_repairs_what_the_model_got_wrong() -> None:
    brief = TripBrief(
        id="x", destination="Lisbon", origin="ARN", start_date=dt.date(2026, 10, 9), end_date=dt.date(2026, 10, 10)
    )
    draft = DraftItinerary(
        stops=[
            DraftStop(day=5, start="10:00", end="12:00", place_name="Nowhere", category="walk", why="", signal_ids=[]),
            DraftStop(
                day=1, start="noon", end="", place_name="Time Out Market", category="FOOD", why="", signal_ids=["ghost"]
            ),
            DraftStop(
                day=0, start="10:00", end="09:00", place_name=" LX Factory ", category="mall", why="", signal_ids=[]
            ),
        ]
    )
    itinerary = to_itinerary(brief, [], draft)
    stops = itinerary.stops()
    assert [stop.place_name for stop in stops] == ["LX Factory", "Time Out Market"]
    assert stops[0].end > stops[0].start
    assert stops[1].start == parse_time("10:00") and stops[1].signal_ids == []
    assert stops[0].category == "sight" and stops[1].category == "food"
