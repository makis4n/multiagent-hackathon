"""Recorded Calendar API tests for creating and finding a trip calendar."""

import datetime as dt
import json
import re
from pathlib import Path

import httpx
import pytest
import respx

from trip_core.models import Day, Itinerary, Stop, TripBrief
from trip_itinerary.calendar import CALENDAR_API_BASE, CALENDAR_TIMEZONE_ENV, CalendarClient, CalendarExporter
from trip_itinerary.credentials import StaticTokenProvider

CASSETTES = Path(__file__).parent / "cassettes" / "calendar_create.json"


def recorded(name: str) -> dict[str, object]:
    cassette: object = json.loads(CASSETTES.read_text(encoding="utf-8"))
    assert isinstance(cassette, dict)
    response: object = cassette[name]
    assert isinstance(response, dict)
    return response


def brief() -> TripBrief:
    return TripBrief(
        id="brief-tokyo",
        destination="Tokyo",
        origin="ARN",
        start_date=dt.date(2026, 11, 12),
        end_date=dt.date(2026, 11, 16),
    )


def itinerary() -> Itinerary:
    return Itinerary(id="it-tokyo-2026-11", brief_id="brief-tokyo")


def itinerary_with_stops() -> Itinerary:
    return Itinerary(
        id="it-tokyo-2026-11",
        brief_id="brief-tokyo",
        days=[
            Day(
                date=dt.date(2026, 11, 12),
                stops=[
                    Stop(
                        id="tsukiji",
                        day=0,
                        start=dt.time(10),
                        end=dt.time(12),
                        place_name="Tsukiji Outer Market",
                        category="food",
                        why="Fresh sushi for breakfast.",
                    ),
                    Stop(
                        id="teamlab",
                        day=0,
                        start=dt.time(14, 30),
                        end=dt.time(16),
                        place_name="teamLab Planets",
                        category="sight",
                        why="Immersive digital art.",
                    ),
                ],
            ),
            Day(
                date=dt.date(2026, 11, 13),
                stops=[
                    Stop(
                        id="yanaka",
                        day=1,
                        start=dt.time(9, 15),
                        end=dt.time(11, 45),
                        place_name="Yanaka Ginza",
                        category="walk",
                        why="A traditional shopping street.",
                    )
                ],
            ),
        ],
    )


def test_creates_a_calendar_and_returns_its_url() -> None:
    with respx.mock(base_url=CALENDAR_API_BASE) as mock:
        listed = mock.get("/users/me/calendarList").mock(
            return_value=httpx.Response(200, json=recorded("empty_calendar_list"))
        )
        created = mock.post("/calendars").mock(return_value=httpx.Response(200, json=recorded("created_calendar")))
        mock.get("/calendars/tokyo-2026-11-12%40group.calendar.google.com/events").mock(
            return_value=httpx.Response(200, json={"items": []})
        )
        with CalendarClient(StaticTokenProvider("fake-token")) as client:
            result = CalendarExporter(client, timezone="Europe/Stockholm").export(itinerary(), brief())

    assert listed.called and created.called
    assert json.loads(created.calls.last.request.content) == {
        "summary": "Tokyo 2026-11-12",
        "timeZone": "Europe/Stockholm",
    }
    assert "tokyo-2026-11-12@group.calendar.google.com" in result


def test_reuses_the_named_calendar_for_the_same_itinerary() -> None:
    with respx.mock(base_url=CALENDAR_API_BASE, assert_all_called=False) as mock:
        listed = mock.get("/users/me/calendarList").mock(
            return_value=httpx.Response(200, json=recorded("existing_calendar_list"))
        )
        created = mock.post("/calendars").mock(return_value=httpx.Response(200, json=recorded("created_calendar")))
        mock.get("/calendars/tokyo-2026-11-12%40group.calendar.google.com/events").mock(
            return_value=httpx.Response(200, json={"items": []})
        )
        with CalendarClient(StaticTokenProvider("fake-token")) as client:
            exporter = CalendarExporter(client, timezone="Europe/Stockholm")
            first = exporter.export(itinerary(), brief())
            second = exporter.export(itinerary(), brief())

    assert listed.call_count == 2
    assert not created.called
    assert first == second


def test_calendar_timezone_defaults_to_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CALENDAR_TIMEZONE_ENV, raising=False)
    with respx.mock(base_url=CALENDAR_API_BASE) as mock:
        mock.get("/users/me/calendarList").mock(return_value=httpx.Response(200, json=recorded("empty_calendar_list")))
        created = mock.post("/calendars").mock(return_value=httpx.Response(200, json=recorded("created_calendar")))
        mock.get("/calendars/tokyo-2026-11-12%40group.calendar.google.com/events").mock(
            return_value=httpx.Response(200, json={"items": []})
        )
        with CalendarClient(StaticTokenProvider("fake-token")) as client:
            CalendarExporter(client).export(itinerary(), brief())

    assert json.loads(created.calls.last.request.content)["timeZone"] == "UTC"


def test_one_event_per_stop_uses_day_dates_and_calendar_timezone() -> None:
    with respx.mock(base_url=CALENDAR_API_BASE) as mock:
        mock.get("/users/me/calendarList").mock(
            return_value=httpx.Response(200, json=recorded("existing_event_calendar_list"))
        )
        mock.get("/calendars/trip-calendar/events").mock(return_value=httpx.Response(200, json={"items": []}))
        inserted = mock.post("/calendars/trip-calendar/events").mock(
            return_value=httpx.Response(200, json=recorded("inserted_event"))
        )
        with CalendarClient(StaticTokenProvider("fake-token")) as client:
            CalendarExporter(client, timezone="Europe/Stockholm").export(itinerary_with_stops(), brief())

    payloads = [json.loads(call.request.content) for call in inserted.calls]
    event_ids = [payload.pop("id") for payload in payloads]
    assert inserted.call_count == 3
    assert len(set(event_ids)) == 3
    assert all(re.fullmatch(r"[a-v0-9]{5,1024}", event_id) for event_id in event_ids)
    assert payloads == [
        {
            "summary": "Tsukiji Outer Market",
            "description": "Fresh sushi for breakfast.\n\nItinerary: it-tokyo-2026-11",
            "extendedProperties": {"private": {"trip_itinerary_id": "it-tokyo-2026-11"}},
            "start": {"dateTime": "2026-11-12T10:00:00", "timeZone": "Europe/Stockholm"},
            "end": {"dateTime": "2026-11-12T12:00:00", "timeZone": "Europe/Stockholm"},
        },
        {
            "summary": "teamLab Planets",
            "description": "Immersive digital art.\n\nItinerary: it-tokyo-2026-11",
            "extendedProperties": {"private": {"trip_itinerary_id": "it-tokyo-2026-11"}},
            "start": {"dateTime": "2026-11-12T14:30:00", "timeZone": "Europe/Stockholm"},
            "end": {"dateTime": "2026-11-12T16:00:00", "timeZone": "Europe/Stockholm"},
        },
        {
            "summary": "Yanaka Ginza",
            "description": "A traditional shopping street.\n\nItinerary: it-tokyo-2026-11",
            "extendedProperties": {"private": {"trip_itinerary_id": "it-tokyo-2026-11"}},
            "start": {"dateTime": "2026-11-13T09:15:00", "timeZone": "Europe/Stockholm"},
            "end": {"dateTime": "2026-11-13T11:45:00", "timeZone": "Europe/Stockholm"},
        },
    ]


def test_aware_stop_times_are_sent_as_offset_free_local_times() -> None:
    aware = dt.timezone(dt.timedelta(hours=2))
    trip = Itinerary(
        id="it-aware-time",
        brief_id="brief-tokyo",
        days=[
            Day(
                date=dt.date(2026, 11, 12),
                stops=[
                    Stop(
                        id="late-breakfast",
                        day=0,
                        start=dt.time(10, 15, tzinfo=aware),
                        end=dt.time(11, 45, tzinfo=aware),
                        place_name="Kissa",
                        category="food",
                        why="A relaxed local breakfast.",
                    )
                ],
            )
        ],
    )
    with respx.mock(base_url=CALENDAR_API_BASE) as mock:
        mock.get("/users/me/calendarList").mock(
            return_value=httpx.Response(200, json=recorded("existing_event_calendar_list"))
        )
        mock.get("/calendars/trip-calendar/events").mock(return_value=httpx.Response(200, json={"items": []}))
        inserted = mock.post("/calendars/trip-calendar/events").mock(
            return_value=httpx.Response(200, json=recorded("inserted_event"))
        )
        with CalendarClient(StaticTokenProvider("fake-token")) as client:
            CalendarExporter(client, timezone="Europe/Stockholm").export(trip, brief())

    payload = json.loads(inserted.calls.last.request.content)
    for key, expected in (("start", "2026-11-12T10:15:00"), ("end", "2026-11-12T11:45:00")):
        date_time = payload[key]["dateTime"]
        assert date_time == expected
        assert "+" not in date_time and not date_time.endswith("Z")


def test_second_export_updates_instead_of_duplicating() -> None:
    trip = itinerary_with_stops()
    with respx.mock(base_url=CALENDAR_API_BASE) as mock:
        mock.get("/users/me/calendarList").mock(
            return_value=httpx.Response(200, json=recorded("existing_event_calendar_list"))
        )
        mock.get("/calendars/trip-calendar/events").mock(return_value=httpx.Response(200, json={"items": []}))
        inserted = mock.post("/calendars/trip-calendar/events").mock(
            side_effect=[
                httpx.Response(200, json=recorded("inserted_event")),
                httpx.Response(200, json=recorded("inserted_event")),
                httpx.Response(200, json=recorded("inserted_event")),
                httpx.Response(409, json={"error": {"status": "ALREADY_EXISTS"}}),
                httpx.Response(409, json={"error": {"status": "ALREADY_EXISTS"}}),
                httpx.Response(409, json={"error": {"status": "ALREADY_EXISTS"}}),
            ]
        )
        updated = mock.put(url__regex=r"/calendars/trip-calendar/events/[a-v0-9]+$").mock(
            return_value=httpx.Response(200, json=recorded("inserted_event"))
        )
        with CalendarClient(StaticTokenProvider("fake-token")) as client:
            exporter = CalendarExporter(client, timezone="Europe/Stockholm")
            exporter.export(trip, brief())
            exporter.export(trip, brief())

    assert inserted.call_count == 6
    assert updated.call_count == 3
    assert len({call.request.url.path.rsplit("/", 1)[-1] for call in updated.calls}) == 3


def test_insert_conflict_falls_back_to_update() -> None:
    trip = itinerary_with_stops()
    with respx.mock(base_url=CALENDAR_API_BASE) as mock:
        mock.get("/users/me/calendarList").mock(
            return_value=httpx.Response(200, json=recorded("existing_event_calendar_list"))
        )
        mock.get("/calendars/trip-calendar/events").mock(return_value=httpx.Response(200, json={"items": []}))
        inserted = mock.post("/calendars/trip-calendar/events").mock(
            side_effect=[
                httpx.Response(409, json={"error": {"status": "ALREADY_EXISTS"}}),
                httpx.Response(200, json=recorded("inserted_event")),
                httpx.Response(200, json=recorded("inserted_event")),
            ]
        )
        updated = mock.put(url__regex=r"/calendars/trip-calendar/events/[a-v0-9]+$").mock(
            return_value=httpx.Response(200, json=recorded("inserted_event"))
        )
        with CalendarClient(StaticTokenProvider("fake-token")) as client:
            CalendarExporter(client, timezone="Europe/Stockholm").export(trip, brief())

    assert inserted.call_count == 3
    assert updated.call_count == 1
    updated_id = updated.calls.last.request.url.path.rsplit("/", 1)[-1]
    assert json.loads(updated.calls.last.request.content)["id"] == updated_id


def test_removed_stop_is_deleted_but_surviving_stop_is_not() -> None:
    original = itinerary_with_stops()
    survivor = original.model_copy(
        update={"days": [Day(date=original.days[0].date, stops=[original.days[0].stops[0]])]}
    )
    removed_id = _event_id_for_test(original.id, original.days[0].stops[1].id)
    surviving_id = _event_id_for_test(original.id, original.days[0].stops[0].id)
    with respx.mock(base_url=CALENDAR_API_BASE) as mock:
        mock.get("/users/me/calendarList").mock(
            return_value=httpx.Response(200, json=recorded("existing_event_calendar_list"))
        )
        events = mock.get("/calendars/trip-calendar/events").mock(
            return_value=httpx.Response(200, json={"items": [{"id": removed_id}, {"id": surviving_id}]})
        )
        deleted = mock.delete(url__regex=rf"/calendars/trip-calendar/events/{removed_id}$").mock(
            return_value=httpx.Response(204)
        )
        mock.post("/calendars/trip-calendar/events").mock(
            return_value=httpx.Response(200, json=recorded("inserted_event"))
        )
        with CalendarClient(StaticTokenProvider("fake-token")) as client:
            CalendarExporter(client, timezone="Europe/Stockholm").export(survivor, brief())

    assert events.calls.last.request.url.params["privateExtendedProperty"] == "trip_itinerary_id=it-tokyo-2026-11"
    assert deleted.call_count == 1
    assert surviving_id not in deleted.calls.last.request.url.path


def test_unverified_stop_is_labelled_with_its_failure_reason() -> None:
    failed_stop = (
        itinerary_with_stops()
        .days[0]
        .stops[0]
        .model_copy(update={"status": "failed", "failure_reason": "The venue could not be verified as open."})
    )
    trip = Itinerary(
        id="it-tokyo-2026-11",
        brief_id="brief-tokyo",
        days=[Day(date=dt.date(2026, 11, 12), stops=[failed_stop])],
    )
    with respx.mock(base_url=CALENDAR_API_BASE) as mock:
        mock.get("/users/me/calendarList").mock(
            return_value=httpx.Response(200, json=recorded("existing_event_calendar_list"))
        )
        mock.get("/calendars/trip-calendar/events").mock(return_value=httpx.Response(200, json={"items": []}))
        inserted = mock.post("/calendars/trip-calendar/events").mock(
            return_value=httpx.Response(200, json=recorded("inserted_event"))
        )
        with CalendarClient(StaticTokenProvider("fake-token")) as client:
            CalendarExporter(client, timezone="Europe/Stockholm").export(trip, brief())

    payload = json.loads(inserted.calls.last.request.content)
    assert payload["summary"] == "Unverified: Tsukiji Outer Market"
    assert "The venue could not be verified as open." in payload["description"]


def test_missing_stale_event_is_already_gone() -> None:
    trip = itinerary_with_stops()
    stale_id = _event_id_for_test(trip.id, "removed-stop")
    with respx.mock(base_url=CALENDAR_API_BASE) as mock:
        mock.get("/users/me/calendarList").mock(
            return_value=httpx.Response(200, json=recorded("existing_event_calendar_list"))
        )
        mock.get("/calendars/trip-calendar/events").mock(
            return_value=httpx.Response(200, json={"items": [{"id": stale_id}]})
        )
        mock.delete(url__regex=rf"/calendars/trip-calendar/events/{stale_id}$").mock(
            return_value=httpx.Response(404, json={"error": {"status": "NOT_FOUND"}})
        )
        inserted = mock.post("/calendars/trip-calendar/events").mock(
            return_value=httpx.Response(200, json=recorded("inserted_event"))
        )
        with CalendarClient(StaticTokenProvider("fake-token")) as client:
            CalendarExporter(client, timezone="Europe/Stockholm").export(trip, brief())

    assert inserted.call_count == 3


def _event_id_for_test(itinerary_id: str, stop_id: str) -> str:
    from trip_itinerary.calendar import _event_id

    return _event_id(itinerary_id, stop_id)
