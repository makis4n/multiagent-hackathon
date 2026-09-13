import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from trip_core import llm
from trip_core.models import (
    BudgetBand,
    Check,
    CheckKind,
    Day,
    Itinerary,
    RetryableError,
    Signal,
    SignalSource,
    Stop,
    TripBrief,
    VerificationReport,
)
from trip_itinerary.planner import GeminiPlanner, build_replace_failed_prompt
from trip_itinerary.schemas import PatchesResponse

RECORDED = Path(__file__).parent / "recorded"

SKIP_QUESTION = "Anything in the plan you would rather skip?"

PLAN = [
    ("stop-00", 0, dt.time(9, 0), dt.time(11, 0), "Tsukiji Outer Market", "food"),
    ("stop-01", 0, dt.time(12, 0), dt.time(14, 0), "Nezu Museum", "museum"),
    ("stop-02", 0, dt.time(20, 0), dt.time(23, 0), "Shibuya Nonbei Yokocho", "nightlife"),
    ("stop-03", 1, dt.time(9, 30), dt.time(11, 0), "Yanaka Ginza", "walk"),
    ("stop-04", 1, dt.time(13, 0), dt.time(15, 0), "teamLab Planets", "museum"),
    ("stop-05", 1, dt.time(20, 0), dt.time(22, 30), "Golden Gai", "nightlife"),
]


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
    days = [Day(date=dt.date(2026, 5, 1)), Day(date=dt.date(2026, 5, 2))]
    for stop_id, day, start, end, place, category in PLAN:
        days[day].stops.append(
            Stop(
                id=stop_id,
                day=day,
                start=start,
                end=end,
                place_name=place,
                category=category,
                why="The signals put this one at the top for this slot.",
                signal_ids=["sig-1"],
            )
        )
    return Itinerary(id="it-tokyo", brief_id="brief-tokyo", days=days)


def report(*stop_ids: str) -> VerificationReport:
    checks = [Check(stop_id=stop_id, check=CheckKind.exists, ok=True) for stop_id, *_ in PLAN]
    for stop_id in stop_ids:
        checks.append(Check(stop_id=stop_id, check=CheckKind.open, ok=False, detail="shut on a Tuesday"))
    return VerificationReport(itinerary_id="it-tokyo", checks=checks)


def signals() -> list[Signal]:
    return [
        Signal(
            id="sig-1",
            source=SignalSource.reddit,
            url="https://reddit.example/tokyo/1",
            title="Quiet gardens in Tokyo",
            excerpt="Kiyosumi Teien stays empty until the middle of the morning.",
            places_mentioned=["Kiyosumi Teien"],
            score=0.8,
        ),
        Signal(
            id="sig-2",
            source=SignalSource.youtube,
            url="https://youtube.example/watch?v=ueno",
            title="Cheap lunch near Ueno",
            excerpt="Ameya Yokocho is still the best value at midday.",
            places_mentioned=["Ameya Yokocho"],
            score=0.7,
        ),
        Signal(
            id="sig-3",
            source=SignalSource.reddit,
            url="https://reddit.example/tokyo/3",
            title="Evening stalls",
            excerpt="The Night Market runs late every day of the week.",
            places_mentioned=["Night Market"],
            score=0.6,
        ),
    ]


def used_places_only() -> list[Signal]:
    """Signals that name nothing the plan does not already hold."""
    return [
        Signal(
            id="sig-3",
            source=SignalSource.reddit,
            url="https://reddit.example/tokyo/3",
            title="The same six places again",
            excerpt="Golden Gai and teamLab Planets are the two everybody names.",
            places_mentioned=["Golden Gai", "teamLab Planets"],
            score=0.5,
        )
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


def test_one_patch_per_failed_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, "replace_failed_tokyo_two.json")
    given = itinerary()
    before = given.model_dump()

    patches = GeminiPlanner().replace_failed(brief(), given, report("stop-01", "stop-04"), signals())

    assert [patch.op for patch in patches] == ["replace", "replace"]
    assert [patch.stop_id for patch in patches] == ["stop-01", "stop-04"]
    assert not {patch.stop_id for patch in patches} & {"stop-00", "stop-02", "stop-03", "stop-05"}
    assert given.model_dump() == before


def test_a_replace_keeps_the_day_and_the_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, "replace_failed_tokyo_two.json")

    patches = GeminiPlanner().replace_failed(brief(), itinerary(), report("stop-01", "stop-04"), signals())

    first, second = patches[0].stop, patches[1].stop
    assert first is not None and second is not None
    assert (first.day, first.start, first.end) == (0, dt.time(12, 0), dt.time(14, 0))
    assert (second.day, second.start, second.end) == (1, dt.time(13, 0), dt.time(15, 0))
    assert [first.place_name, second.place_name] == ["Kiyosumi Teien", "Ameya Yokocho"]


def test_drops_a_patch_naming_a_stop_that_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, "replace_failed_tokyo_stray.json")
    planner = GeminiPlanner()

    patches = planner.replace_failed(brief(), itinerary(), report("stop-01", "stop-04"), signals())

    assert [patch.stop_id for patch in patches] == ["stop-01", "stop-04"]
    assert planner.last_dropped == ["failed-stop patch 1: names no failed stop: 'stop-00'"]


def test_no_candidate_becomes_a_remove(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, "replace_failed_tokyo_reused.json")
    planner = GeminiPlanner()

    patches = planner.replace_failed(brief(), itinerary(), report("stop-01", "stop-04"), used_places_only())

    assert [patch.op for patch in patches] == ["remove", "remove"]
    assert [patch.stop_id for patch in patches] == ["stop-01", "stop-04"]
    assert all(patch.stop is None for patch in patches)
    assert planner.last_dropped == [
        "failed stop stop-01: 'Golden Gai' is already in the plan or skipped, removed instead",
        "failed stop stop-04: 'teamlab planets' is already in the plan or skipped, removed instead",
    ]


def test_never_reuses_a_skipped_place(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, "replace_failed_tokyo_skipped.json")
    planner = GeminiPlanner()
    given = brief(answers={SKIP_QUESTION: "skip: Night Market"})

    patches = planner.replace_failed(given, itinerary(), report("stop-01", "stop-04"), signals())

    names = [patch.stop.place_name.casefold() for patch in patches if patch.stop is not None]
    assert "night market" not in names
    assert [patch.op for patch in patches] == ["remove", "replace"]
    assert names == ["kiyosumi teien"]
    assert planner.last_dropped == [
        "failed stop stop-01: 'Night market' is already in the plan or skipped, removed instead"
    ]


def test_two_patches_for_one_failed_stop_keeps_the_first(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, "replace_failed_tokyo_duplicate.json")
    planner = GeminiPlanner()

    patches = planner.replace_failed(brief(), itinerary(), report("stop-01", "stop-04"), signals())

    assert [patch.stop_id for patch in patches] == ["stop-01", "stop-04"]
    first = patches[0].stop
    assert first is not None and first.place_name == "Kiyosumi Teien"
    assert planner.last_dropped == ["failed-stop patch 1: a second patch for stop-01, kept the first"]


def test_uses_the_main_model_and_the_flat_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = install(monkeypatch, "replace_failed_tokyo_two.json")

    GeminiPlanner().replace_failed(brief(), itinerary(), report("stop-01"), signals())

    call = stub.calls[0]
    assert call["model"] == llm.model_main()
    assert call["schema"] is PatchesResponse


def test_no_failed_stop_asks_the_model_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = install(monkeypatch, "replace_failed_tokyo_two.json")

    patches = GeminiPlanner().replace_failed(brief(), itinerary(), report(), signals())

    assert patches == []
    assert stub.calls == []


def test_the_prompt_is_readable_without_a_model() -> None:
    given = brief(answers={SKIP_QUESTION: "skip: Night Market"})

    prompt = build_replace_failed_prompt(given, itinerary(), report("stop-01"), signals())

    assert "stop-01 Nezu Museum 12:00 to 14:00: failed open (shut on a Tuesday)" in prompt
    assert "- Golden Gai" in prompt
    assert "- night market" in prompt
    assert "Kiyosumi Teien" in prompt
    assert "—" not in prompt


def test_model_failure_returns_no_patches(monkeypatch: pytest.MonkeyPatch) -> None:
    def raiser(prompt: str, schema: type[BaseModel], **kwargs: Any) -> BaseModel:
        raise RetryableError("gemini 429: rate limited")

    monkeypatch.setattr(llm, "complete_json", raiser)
    planner = GeminiPlanner()
    given = itinerary()
    before = given.model_dump()

    patches = planner.replace_failed(brief(), given, report("stop-01"), signals())

    assert patches == []
    assert given.model_dump() == before
    assert planner.last_dropped == ["replace_failed: no patches: the model call raised RetryableError"]


def test_a_stop_the_model_says_nothing_about_becomes_a_remove(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, "replace_failed_tokyo_silent.json")
    planner = GeminiPlanner()

    patches = planner.replace_failed(brief(), itinerary(), report("stop-01", "stop-04"), signals())

    assert [patch.stop_id for patch in patches] == ["stop-01", "stop-04"]
    assert [patch.op for patch in patches] == ["remove", "replace"]
    assert patches[0].stop is None
    assert planner.last_dropped == ["failed stop stop-01: the model proposed nothing, removed instead"]


def test_two_failed_stops_do_not_share_one_replacement(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, "replace_failed_tokyo_same_place.json")
    planner = GeminiPlanner()

    patches = planner.replace_failed(brief(), itinerary(), report("stop-01", "stop-04"), signals())

    assert [patch.op for patch in patches] == ["replace", "remove"]
    assert [patch.stop.place_name for patch in patches if patch.stop is not None] == ["Kiyosumi Teien"]
    assert planner.last_dropped == [
        "failed stop stop-04: 'Kiyosumi Teien' is already in the plan or skipped, removed instead"
    ]


def test_one_stop_failing_two_checks_yields_one_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, "replace_failed_tokyo_one_stop.json")
    twice = report("stop-01")
    twice.checks.append(Check(stop_id="stop-01", check=CheckKind.reachable, ok=False, detail="55 minutes away"))

    planner = GeminiPlanner()

    patches = planner.replace_failed(brief(), itinerary(), twice, signals())

    assert len(patches) == 1
    assert (patches[0].op, patches[0].stop_id) == ("replace", "stop-01")
    assert planner.last_dropped == []
