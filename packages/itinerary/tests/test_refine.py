import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from trip_core import llm
from trip_core.models import (
    BudgetBand,
    Day,
    Itinerary,
    ItineraryPatch,
    RetryableError,
    Signal,
    SignalSource,
    Stop,
    ToolError,
    TripBrief,
)
from trip_itinerary.planner import MAX_PATCHES, GeminiPlanner, build_refine_prompt
from trip_itinerary.schemas import PatchesResponse

RECORDED = Path(__file__).parent / "recorded"
PLANTED = "PLANTED-FAKE-TOKEN-abc123"

ANSWERS = {
    "Do you want early starts, or should mornings stay slow?": "Slow mornings.",
    "Should the Shibuya nightlife stop run late, or end by 22:00?": "End by 22:00.",
}


def recorded(name: str) -> PatchesResponse:
    return PatchesResponse.model_validate(json.loads((RECORDED / name).read_text()))


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


def signals() -> list[Signal]:
    return [
        Signal(
            id="sig-1",
            source=SignalSource.reddit,
            url="https://reddit.example/tokyo/1",
            title="Best first morning in Tokyo",
            excerpt="Tsukiji early, then the Nezu garden when it opens.",
            places_mentioned=["Tsukiji Outer Market", "Nezu Museum"],
            score=0.8,
        ),
        Signal(
            id="sig-2",
            source=SignalSource.youtube,
            url="https://youtube.example/watch?v=tokyo",
            title="Cheap nights in Shibuya",
            excerpt="The alley bars are still the best value after 20:00.",
            places_mentioned=["Shibuya Nonbei Yokocho", "Yanaka Ginza"],
            score=0.6,
        ),
    ]


class Stub:
    """Stands in for trip_core.llm.complete_json and records how it was called."""

    def __init__(self, response: PatchesResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def __call__(self, prompt: str, schema: type[BaseModel], **kwargs: Any) -> BaseModel:
        self.calls.append({"prompt": prompt, "schema": schema, **kwargs})
        return self.response


def install(monkeypatch: pytest.MonkeyPatch, name: str) -> Stub:
    stub = Stub(recorded(name))
    monkeypatch.setattr(llm, "complete_json", stub)
    return stub


def test_returns_patches_not_an_itinerary(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = install(monkeypatch, "refine_tokyo_remove_and_add.json")
    given = itinerary()
    before = given.model_dump()

    patches = GeminiPlanner().refine(brief(), given, ANSWERS, signals())

    assert len(stub.calls) == 1
    assert isinstance(patches, list)
    assert [type(patch) for patch in patches] == [ItineraryPatch, ItineraryPatch]
    assert [patch.op for patch in patches] == ["remove", "add"]
    assert given.model_dump() == before
    assert given.version == 1


def test_uses_the_main_model_and_the_flat_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = install(monkeypatch, "refine_tokyo_remove_and_add.json")

    GeminiPlanner().refine(brief(), itinerary(), ANSWERS, signals())

    call = stub.calls[0]
    assert call["model"] == llm.model_main()
    assert call["schema"] is PatchesResponse
    assert "Slow mornings." in call["prompt"]
    assert "sig-1" in call["prompt"]


def test_drops_a_patch_that_does_not_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, "refine_tokyo_unapplicable.json")
    planner = GeminiPlanner()

    patches = planner.refine(brief(), itinerary(), ANSWERS, signals())

    assert [patch.op for patch in patches] == ["remove", "add"]
    assert patches[0].stop_id == "stop-00"
    assert patches[1].stop is not None and patches[1].stop.id == "stop-03"
    assert len(planner.last_dropped) == 2
    assert any("stop-00" in line for line in planner.last_dropped)
    assert any("does not apply: no day 9" in line for line in planner.last_dropped)
    assert all(line.startswith("candidate patch ") for line in planner.last_dropped)


def test_strips_invented_signal_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, "refine_tokyo_invented_signal.json")

    patches = GeminiPlanner().refine(brief(), itinerary(), ANSWERS, signals())

    assert len(patches) == 1
    stop = patches[0].stop
    assert stop is not None
    assert stop.signal_ids == ["sig-1", "sig-2"]


def test_caps_the_patch_count(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, "refine_tokyo_twelve.json")
    planner = GeminiPlanner()

    patches = planner.refine(brief(), itinerary(), ANSWERS, signals())

    assert len(patches) == MAX_PATCHES == 8
    assert [patch.stop.id for patch in patches if patch.stop is not None] == [f"stop-1{index}" for index in range(8)]
    assert len(planner.last_dropped) == 4
    assert all("cap" in line for line in planner.last_dropped)


def test_last_dropped_resets_between_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    planner = GeminiPlanner()
    install(monkeypatch, "refine_tokyo_unapplicable.json")
    planner.refine(brief(), itinerary(), ANSWERS, signals())
    assert planner.last_dropped

    install(monkeypatch, "refine_tokyo_remove_and_add.json")
    planner.refine(brief(), itinerary(), ANSWERS, signals())

    assert planner.last_dropped == []


def test_the_prompt_is_readable_without_a_model() -> None:
    prompt = build_refine_prompt(brief(), itinerary(), ANSWERS, signals())

    assert "Tokyo" in prompt
    assert "stop-00 09:00 to 11:00 Tsukiji Outer Market" in prompt
    assert "End by 22:00." in prompt
    assert "Cheap nights in Shibuya" in prompt
    assert "—" not in prompt


def test_an_answer_from_this_round_is_not_also_shown_as_an_earlier_one() -> None:
    """The loop merges the new answers into the brief before calling refine, so both headings would show them."""
    just_given = {"Anything to skip?": "skip: Shibuya Sky"}
    merged = brief(answers={**ANSWERS, **just_given})

    prompt = build_refine_prompt(merged, itinerary(), just_given, signals())

    assert prompt.count("skip: Shibuya Sky") == 1
    assert "Slow mornings." in prompt


class Raiser:
    """Stands in for complete_json and fails the way the provider fails."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def __call__(self, prompt: str, schema: type[BaseModel], **kwargs: Any) -> BaseModel:
        self.calls += 1
        raise self.error


def test_model_failure_returns_no_patches(monkeypatch: pytest.MonkeyPatch) -> None:
    raiser = Raiser(RetryableError("gemini 429: rate limited"))
    monkeypatch.setattr(llm, "complete_json", raiser)
    planner = GeminiPlanner()
    given = itinerary()
    before = given.model_dump()

    patches = planner.refine(brief(), given, ANSWERS, signals())

    assert raiser.calls == 1
    assert patches == []
    assert given.model_dump() == before
    assert planner.last_dropped == ["refine: no patches: the model call raised RetryableError"]


def test_model_output_that_does_not_validate_returns_no_patches(monkeypatch: pytest.MonkeyPatch) -> None:
    def invalid(prompt: str, schema: type[BaseModel], **kwargs: Any) -> BaseModel:
        return PatchesResponse.model_validate({"patches": [{"op": 5}]})

    monkeypatch.setattr(llm, "complete_json", invalid)
    planner = GeminiPlanner()

    patches = planner.refine(brief(), itinerary(), ANSWERS, signals())

    assert patches == []
    assert planner.last_dropped == ["refine: no patches: the model call raised ValidationError"]


def test_a_mapping_drop_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, "refine_tokyo_unknown_op.json")
    planner = GeminiPlanner()

    patches = planner.refine(brief(), itinerary(), ANSWERS, signals())

    assert [patch.op for patch in patches] == ["remove"]
    assert any("unknown op" in line and "'delete'" in line for line in planner.last_dropped)
    assert all(line.startswith("model patch ") for line in planner.last_dropped)


def test_the_log_never_carries_the_model_message(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Rule 12: the stack, not the message. A provider message can quote the model's own output."""
    monkeypatch.setattr(llm, "complete_json", Raiser(ToolError(f"gemini 400: rejected {PLANTED}")))
    planner = GeminiPlanner()

    with caplog.at_level(logging.DEBUG, logger="trip_itinerary.planner"):
        patches = planner.refine(brief(), itinerary(), ANSWERS, signals())

    assert patches == []
    assert PLANTED not in caplog.text
    assert all(PLANTED not in line for line in planner.last_dropped)
    assert "ToolError" in caplog.text
