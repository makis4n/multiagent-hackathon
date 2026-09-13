"""Recorded Calendar API tests for creating and finding a trip calendar."""

import datetime as dt
import json
from pathlib import Path

import httpx
import pytest
import respx

from trip_core.models import Itinerary, TripBrief
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


def test_creates_a_calendar_and_returns_its_url() -> None:
    with respx.mock(base_url=CALENDAR_API_BASE) as mock:
        listed = mock.get("/users/me/calendarList").mock(
            return_value=httpx.Response(200, json=recorded("empty_calendar_list"))
        )
        created = mock.post("/calendars").mock(return_value=httpx.Response(200, json=recorded("created_calendar")))
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
        with CalendarClient(StaticTokenProvider("fake-token")) as client:
            CalendarExporter(client).export(itinerary(), brief())

    assert json.loads(created.calls.last.request.content)["timeZone"] == "UTC"
