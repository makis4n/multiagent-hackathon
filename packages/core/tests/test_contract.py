import datetime as dt

import pytest

from trip_core.fakes import FakePlanner, FakeResearch
from trip_core.models import (
    Check,
    CheckKind,
    Itinerary,
    ItineraryPatch,
    OpeningRange,
    Place,
    Signal,
    Stop,
    TripBrief,
    VerificationReport,
    apply_patch,
    load_fixture,
)


def draft() -> tuple[TripBrief, list[Signal], Itinerary]:
    fixture = load_fixture("tokyo")
    signals = FakeResearch(fixture.signals, fixture.brief.destination).search(fixture.brief)
    return fixture.brief, signals, FakePlanner().draft(fixture.brief, signals)


def test_fixture_loads() -> None:
    fixture = load_fixture("tokyo")
    assert fixture.brief.nights == 4
    assert len(fixture.brief.dates) == 5
    assert len(fixture.signals) == 18
    assert len({signal.url for signal in fixture.signals}) == 18


def test_brief_rejects_reversed_dates() -> None:
    with pytest.raises(ValueError):
        TripBrief(
            id="x", destination="Oslo", origin="ARN", start_date=dt.date(2026, 5, 2), end_date=dt.date(2026, 5, 1)
        )


def test_draft_has_one_day_per_date() -> None:
    brief, _, itinerary = draft()
    assert [day.date for day in itinerary.days] == brief.dates
    assert all(stop.day == index for index, day in enumerate(itinerary.days) for stop in day.stops)


def test_patch_remove_is_pure_and_bumps_version() -> None:
    _, _, itinerary = draft()
    patched = apply_patch(itinerary, ItineraryPatch(op="remove", stop_id="stop-00"))
    assert patched.version == itinerary.version + 1
    assert "stop-00" not in [stop.id for stop in patched.stops()]
    assert "stop-00" in [stop.id for stop in itinerary.stops()]


def test_patch_move_rewrites_day() -> None:
    _, _, itinerary = draft()
    patched = apply_patch(itinerary, ItineraryPatch(op="move", stop_id="stop-00", target_day=1, position=0))
    moved = patched.days[1].stops[0]
    assert moved.id == "stop-00"
    assert moved.day == 1


def test_patch_replace_and_add() -> None:
    _, _, itinerary = draft()
    new = Stop(id="new", day=9, start=dt.time(9), end=dt.time(10), place_name="Anywhere", category="walk", why="")
    replaced = apply_patch(itinerary, ItineraryPatch(op="replace", stop_id="stop-01", stop=new))
    day_index, stop_index = replaced.locate("new")
    assert (day_index, stop_index) == (0, 1)
    assert replaced.days[0].stops[1].day == 0
    added = apply_patch(itinerary, ItineraryPatch(op="add", stop=new, target_day=2))
    assert added.days[2].stops[-1].id == "new"


def test_patch_rejects_bad_input() -> None:
    _, _, itinerary = draft()
    with pytest.raises(ValueError):
        apply_patch(itinerary, ItineraryPatch(op="add", target_day=0))
    with pytest.raises(KeyError):
        apply_patch(itinerary, ItineraryPatch(op="remove", stop_id="missing"))


def test_report_pass_rate() -> None:
    report = VerificationReport(
        itinerary_id="it",
        checks=[
            Check(stop_id="a", check=CheckKind.exists, ok=True),
            Check(stop_id="a", check=CheckKind.open, ok=True),
            Check(stop_id="b", check=CheckKind.exists, ok=True),
            Check(stop_id="b", check=CheckKind.open, ok=False, detail="closed"),
        ],
    )
    assert not report.passed
    assert report.failed_stop_ids() == ["b"]
    assert report.pass_rate() == 0.5


def test_place_is_open() -> None:
    monday_only = Place(
        id="p", name="P", lat=0, lng=0, opening_hours={0: [OpeningRange(open=dt.time(9), close=dt.time(17))]}
    )
    monday, sunday = dt.date(2026, 9, 14), dt.date(2026, 9, 13)
    assert monday_only.is_open(monday, dt.time(10)) is True
    assert monday_only.is_open(monday, dt.time(18)) is False
    assert monday_only.is_open(sunday, dt.time(10)) is False
    assert Place(id="q", name="Q", lat=0, lng=0).is_open(monday, dt.time(10)) is None


def test_airports_use_the_code_and_fall_back_to_the_name() -> None:
    fixture = load_fixture("tokyo")
    assert fixture.brief.airports == ("ARN", "TYO")
    plain = fixture.brief.model_copy(update={"destination_code": None, "origin": "arn "})
    assert plain.airports == ("ARN", "TOKYO")
