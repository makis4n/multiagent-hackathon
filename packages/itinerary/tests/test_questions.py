import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from trip_core import llm
from trip_core.models import MAX_QUESTIONS, BudgetBand, Day, Itinerary, Stop, ToolError, TripBrief
from trip_itinerary.planner import GeminiPlanner, build_questions_prompt
from trip_itinerary.schemas import QuestionsResponse

RECORDED = Path(__file__).parent / "recorded"

EARLY_STARTS = "Do you want early starts, or should mornings stay slow?"
FOOD_AVOIDED = "Any food you avoid, so the Tsukiji and izakaya stops can be swapped?"


def recorded(name: str) -> QuestionsResponse:
    return QuestionsResponse.model_validate(json.loads((RECORDED / name).read_text()))


def brief(**overrides: Any) -> TripBrief:
    fields: dict[str, Any] = {
        "id": "brief-tokyo",
        "destination": "Tokyo",
        "origin": "LIS",
        "start_date": dt.date(2026, 5, 1),
        "end_date": dt.date(2026, 5, 4),
        "travellers": 2,
        "budget_band": BudgetBand.mid,
        "styles": ["food", "art"],
    }
    fields.update(overrides)
    return TripBrief(**fields)


def itinerary() -> Itinerary:
    stops = [
        Stop(
            id="stop-00",
            day=0,
            start=dt.time(9, 0),
            end=dt.time(11, 0),
            place_name="Tsukiji Outer Market",
            category="food",
            why="Three threads called it the best first morning in the city.",
            signal_ids=["sig-1"],
        ),
        Stop(
            id="stop-01",
            day=0,
            start=dt.time(20, 0),
            end=dt.time(23, 0),
            place_name="Shibuya Nonbei Yokocho",
            category="nightlife",
            why="A recent video called the alley bars the cheapest good night out.",
            signal_ids=["sig-2"],
        ),
    ]
    return Itinerary(
        id="it-tokyo",
        brief_id="brief-tokyo",
        days=[Day(date=dt.date(2026, 5, 1), stops=stops), Day(date=dt.date(2026, 5, 2))],
    )


class Stub:
    """Stands in for trip_core.llm.complete_json and records how it was called."""

    def __init__(self, response: QuestionsResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def __call__(self, prompt: str, schema: type[BaseModel], **kwargs: Any) -> BaseModel:
        self.calls.append({"prompt": prompt, "schema": schema, **kwargs})
        return self.response


def install(monkeypatch: pytest.MonkeyPatch, name: str) -> Stub:
    stub = Stub(recorded(name))
    monkeypatch.setattr(llm, "complete_json", stub)
    return stub


def test_caps_at_four(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = install(monkeypatch, "questions_tokyo_seven.json")

    asked = GeminiPlanner().questions(brief(), itinerary())

    assert len(stub.calls) == 1
    assert len(asked) == MAX_QUESTIONS == 4
    assert asked == stub.response.questions[:4]


def test_uses_the_fast_model_and_the_flat_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = install(monkeypatch, "questions_tokyo_seven.json")

    GeminiPlanner().questions(brief(), itinerary())

    call = stub.calls[0]
    assert call["model"] == llm.model_fast()
    assert call["schema"] is QuestionsResponse
    assert "Tokyo" in call["prompt"]
    assert "Shibuya Nonbei Yokocho" in call["prompt"]


def test_skips_answered_questions(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = {
        f"  {EARLY_STARTS.upper()}  ": "Slow mornings.",
        FOOD_AVOIDED: "No shellfish.",
    }
    stub = install(monkeypatch, "questions_tokyo_repeats.json")

    asked = GeminiPlanner().questions(brief(answers=answers), itinerary())

    assert len(stub.calls) == 1
    assert asked == [
        "Should the Shibuya nightlife stop run late, or end by 22:00?",
        "Is one museum a day enough, or do you want two?",
    ]


def test_the_prompt_is_readable_without_a_model() -> None:
    prompt = build_questions_prompt(brief(answers={FOOD_AVOIDED: "No shellfish."}), itinerary())

    assert FOOD_AVOIDED in prompt
    assert "No shellfish." in prompt
    assert "2026-05-01 to 2026-05-04" in prompt
    assert "food, art" in prompt
    assert "stop-00 09:00 to 11:00 Tsukiji Outer Market" in prompt
    assert "—" not in prompt


def test_model_failure_returns_no_questions(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def raiser(prompt: str, schema: type[BaseModel], **kwargs: Any) -> BaseModel:
        nonlocal calls
        calls += 1
        raise ToolError("gemini 400: bad request")

    monkeypatch.setattr(llm, "complete_json", raiser)
    planner = GeminiPlanner()

    asked = planner.questions(brief(), itinerary())

    assert calls == 1
    assert asked == []
    assert any("ToolError" in line for line in planner.last_dropped)
    assert any("no questions" in line for line in planner.last_dropped)


def test_model_output_that_does_not_validate_returns_no_questions(monkeypatch: pytest.MonkeyPatch) -> None:
    def invalid(prompt: str, schema: type[BaseModel], **kwargs: Any) -> BaseModel:
        return QuestionsResponse.model_validate({"questions": [1]})

    monkeypatch.setattr(llm, "complete_json", invalid)
    planner = GeminiPlanner()

    asked = planner.questions(brief(), itinerary())

    assert asked == []
    assert any("ValidationError" in line for line in planner.last_dropped)
