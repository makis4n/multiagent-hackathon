"""The Calendar factory builds offline; OAuth credentials are read only by export."""

import datetime as dt

import pytest

from trip_core.models import Itinerary, ToolError, TripBrief
from trip_itinerary import build_calendar
from trip_itinerary.calendar import CalendarClient, CalendarExporter


def test_build_calendar_reads_credentials_only_on_export(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_CALENDAR_CREDENTIALS_JSON", raising=False)

    calendar = build_calendar()

    assert isinstance(calendar, CalendarExporter)
    assert isinstance(calendar._client, CalendarClient)
    with pytest.raises(ToolError, match=r"GOOGLE_CALENDAR_CREDENTIALS_JSON.*\.env"):
        calendar.export(
            Itinerary(id="itinerary-id", brief_id="brief-id"),
            TripBrief(
                id="brief-id",
                destination="Tokyo",
                origin="ARN",
                start_date=dt.date(2026, 11, 12),
                end_date=dt.date(2026, 11, 16),
            ),
        )
