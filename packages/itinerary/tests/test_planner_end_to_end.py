"""The loop over the tokyo fixture with the planner from build_planner(), every model call stubbed.

Lane A owns the loop; this test only imports it. No network, no key, no model call.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from trip_agent.log import CallLog
from trip_agent.loop import Tools, run
from trip_core import llm
from trip_core.fakes import default_fakes
from trip_core.models import BookingOption, Itinerary, load_fixture
from trip_itinerary import build_planner
from trip_itinerary.draft import DraftItinerary
from trip_itinerary.schemas import PatchesResponse, QuestionsResponse

RECORDED = Path(__file__).parent / "recorded"
CASSETTES = Path(__file__).parent / "cassettes"


def recorded(name: str, schema: type[BaseModel]) -> BaseModel:
    return schema.model_validate(json.loads((RECORDED / name).read_text()))


class Stub:
    """Stands in for trip_core.llm.complete_json, answering by schema and by call order."""

    def __init__(self) -> None:
        self.calls: list[type[BaseModel]] = []

    def __call__(self, prompt: str, schema: type[BaseModel], **kwargs: Any) -> BaseModel:
        self.calls.append(schema)
        if schema is DraftItinerary:
            return schema.model_validate(json.loads((CASSETTES / "tokyo_DraftItinerary.json").read_text()))
        if schema is QuestionsResponse:
            return recorded("e2e_tokyo_questions.json", QuestionsResponse)
        if schema is PatchesResponse:
            patch_calls = [call for call in self.calls if call is PatchesResponse]
            name = "e2e_tokyo_refine.json" if len(patch_calls) == 1 else "e2e_tokyo_replace_failed.json"
            return recorded(name, PatchesResponse)
        raise AssertionError(f"no recorded payload for {schema.__name__}")


def confirm(option: BookingOption) -> dt.datetime:
    return dt.datetime(2026, 9, 13, 10, 0, tzinfo=dt.UTC)


def decline(option: BookingOption) -> dt.datetime | None:
    """Nothing is ordered without a confirmation, so this run books nothing and still finishes."""
    return None


def test_fixture_runs_with_the_real_planner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    stub = Stub()
    monkeypatch.setattr(llm, "complete_json", stub)
    fixture = load_fixture("tokyo")
    fakes = default_fakes()
    tools = Tools(
        research=list(fakes.research),
        resolver=fakes.resolver,
        planner=build_planner(),
        verifier=fakes.verifier,
        booking=fakes.booking,
        calendar=fakes.calendar,
    )

    state = run(fixture.brief, tools, CallLog(tmp_path / "calls.jsonl", fixture.brief.id), confirm=decline)

    assert state.itinerary is not None
    assert stub.calls[:2] == [DraftItinerary, QuestionsResponse]
    assert PatchesResponse in stub.calls
    assert len(state.questions) == 4
    names = [stop.place_name for stop in state.itinerary.stops()]
    assert "Shibuya Sky" not in names
    assert state.calendar_url


def test_the_run_books_only_what_the_user_confirmed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(llm, "complete_json", Stub())
    fixture = load_fixture("tokyo")
    fakes = default_fakes()
    tools = Tools(
        research=list(fakes.research),
        resolver=fakes.resolver,
        planner=build_planner(),
        verifier=fakes.verifier,
        booking=fakes.booking,
        calendar=fakes.calendar,
    )

    state = run(fixture.brief, tools, CallLog(tmp_path / "calls.jsonl", fixture.brief.id), confirm=confirm)

    assert state.orders
    assert all(order.confirmed_by_user_at is not None for order in state.orders)


def test_build_planner_satisfies_every_planner_member(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "complete_json", Stub())
    planner = build_planner()
    fixture = load_fixture("tokyo")

    itinerary = planner.draft(fixture.brief, fixture.signals)

    assert isinstance(itinerary, Itinerary)
    assert len(itinerary.days) == len(fixture.brief.dates)
    assert itinerary.stops()
    for member in ("draft", "questions", "refine", "replace_failed"):
        assert callable(getattr(planner, member))

    assert len(planner.questions(fixture.brief, itinerary)) == 4


def test_the_package_logger_has_a_null_handler() -> None:
    """A library attaches a NullHandler; a handled degrade must not print a stack through the last-resort handler."""
    handlers = logging.getLogger("trip_itinerary").handlers

    assert any(isinstance(handler, logging.NullHandler) for handler in handlers)
