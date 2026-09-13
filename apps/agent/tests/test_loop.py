import datetime as dt
from pathlib import Path

from trip_agent.log import CallLog
from trip_agent.loop import Tools, run
from trip_core.fakes import FakeSet, default_fakes
from trip_core.models import BookingKind, StopStatus, TripBrief, idempotency_key, load_fixture

NOW = dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC)


def tools_from(fakes: FakeSet) -> Tools:
    return Tools(
        research=list(fakes.research),
        resolver=fakes.resolver,
        planner=fakes.planner,
        verifier=fakes.verifier,
        booking=fakes.booking,
        calendar=fakes.calendar,
    )


def test_fixture_runs_end_to_end(tmp_path: Path) -> None:
    fakes = default_fakes()
    brief = load_fixture("tokyo").brief
    log = CallLog(tmp_path / "calls.jsonl", brief.id)
    state = run(brief, tools_from(fakes), log, confirm=lambda option: NOW)

    assert state.itinerary is not None and len(state.itinerary.days) == 5
    assert state.report is not None and state.report.passed
    stops = state.itinerary.stops()
    assert all(stop.status == StopStatus.verified for stop in stops)
    assert not any("(closed)" in stop.place_name for stop in stops)
    assert "Shibuya Sky" not in [stop.place_name for stop in stops]
    assert [order.option.kind for order in state.orders] == [BookingKind.flight, BookingKind.stay]
    assert all(order.confirmed_by_user_at == NOW for order in state.orders)
    assert state.calendar_url
    called = {entry["tool"] for entry in log.entries()}
    assert {
        "research.fake",
        "planner.draft",
        "planner.questions",
        "planner.refine",
        "places.resolve",
        "verifier.verify",
        "planner.replace_failed",
        "booking.search.flight",
        "booking.order.flight",
        "booking.order.stay",
        "calendar.export",
    } <= called


def test_no_confirmation_means_no_order(tmp_path: Path) -> None:
    fakes = default_fakes()
    brief = load_fixture("tokyo").brief
    state = run(brief, tools_from(fakes), CallLog(tmp_path / "calls.jsonl", brief.id), confirm=lambda option: None)
    assert state.orders == []
    assert fakes.booking.order_calls == 0
    assert any("not confirmed" in error for error in state.errors)


def test_retry_keeps_exactly_one_order(tmp_path: Path) -> None:
    fakes = default_fakes()
    brief = load_fixture("tokyo").brief
    flight = fakes.booking.search(brief, BookingKind.flight)[0]
    key = idempotency_key(brief.id, flight)
    fakes.booking.fail_once.add(key)
    log = CallLog(tmp_path / "calls.jsonl", brief.id)
    state = run(brief, tools_from(fakes), log, confirm=lambda option: NOW)
    assert len(state.orders) == 2
    assert len(fakes.booking.orders) == 2
    attempts = [(entry["attempt"], entry["ok"]) for entry in log.entries() if entry["tool"] == "booking.order.flight"]
    assert attempts == [(1, False), (2, True)]


def test_ask_fills_answers_and_patches(tmp_path: Path) -> None:
    fakes = default_fakes()
    brief = TripBrief(
        id="lisbon", destination="Lisbon", origin="ARN", start_date=dt.date(2026, 10, 9), end_date=dt.date(2026, 10, 12)
    )
    asked: list[str] = []

    def ask(question: str) -> str | None:
        asked.append(question)
        return "skip: Lisbon Central Market" if question == "Anything to skip?" else None

    state = run(brief, tools_from(fakes), CallLog(tmp_path / "calls.jsonl", brief.id), confirm=lambda o: NOW, ask=ask)
    assert asked == state.questions
    assert state.brief.answers == {"Anything to skip?": "skip: Lisbon Central Market"}
    assert state.itinerary is not None
    assert "Lisbon Central Market" not in [stop.place_name for stop in state.itinerary.stops()]
    assert state.report is not None and state.report.passed
