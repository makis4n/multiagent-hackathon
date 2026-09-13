"""The transport layer of the calendar export: status mapping, transport failures, and nothing leaked.

Every call is intercepted by respx, so no test opens a socket. MARKER stands for whatever a real error body might
carry: it must never reach an exception message or a log line.
"""

import json
import logging
from pathlib import Path

import httpx
import pytest
import respx

from trip_core.models import RetryableError, ToolError
from trip_itinerary.calendar import CALENDAR_API_BASE, CalendarClient, CalendarNotFound
from trip_itinerary.credentials import StaticTokenProvider

TOKEN = "fake-token"
MARKER = "leaked-body-marker"
CASSETTES = Path(__file__).parent / "cassettes" / "calendar_statuses.json"


def error_body(code: int, status: str) -> dict[str, object]:
    """The Calendar error shape plus the Google error model status string, with the marker in the free text."""
    return {
        "error": {
            "code": code,
            "message": f"{MARKER} in the message",
            "status": status,
            "errors": [{"domain": "calendar", "reason": "someReason", "message": f"{MARKER} again"}],
        }
    }


def client() -> CalendarClient:
    return CalendarClient(StaticTokenProvider(TOKEN))


def status_cassette(name: str) -> dict[str, object]:
    recorded: object = json.loads(CASSETTES.read_text(encoding="utf-8"))
    assert isinstance(recorded, dict)
    body: object = recorded[name]
    assert isinstance(body, dict)
    return body


def test_status_codes(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    with respx.mock(base_url=CALENDAR_API_BASE) as mock:
        unavailable = mock.get("/calendars/one").mock(
            return_value=httpx.Response(503, json=status_cassette("unavailable"))
        )
        forbidden = mock.get("/calendars/two").mock(return_value=httpx.Response(403, json=status_cassette("forbidden")))
        bad = mock.get("/calendars/three").mock(return_value=httpx.Response(400, json=status_cassette("invalid")))
        with client() as calendar:
            with pytest.raises(RetryableError) as retryable:
                calendar.request("GET", "/calendars/one")
            with pytest.raises(ToolError) as denied:
                calendar.request("GET", "/calendars/two")
            with pytest.raises(ToolError) as invalid:
                calendar.request("GET", "/calendars/three")
        assert unavailable.called and forbidden.called and bad.called
        assert mock.calls.call_count == 3

    assert "503" in str(retryable.value)
    assert "re-authorise" in str(denied.value)
    assert "400" in str(invalid.value)
    assert "INVALID_ARGUMENT" in str(invalid.value)
    assert not isinstance(invalid.value, RetryableError)
    for caught in (retryable, denied, invalid):
        assert MARKER not in str(caught.value)
        assert MARKER not in repr(caught.value)
    assert MARKER not in caplog.text
    assert TOKEN not in caplog.text


def test_rate_limit_is_retryable() -> None:
    with respx.mock(base_url=CALENDAR_API_BASE) as mock:
        route = mock.post("/calendars").mock(
            return_value=httpx.Response(429, json=error_body(429, "RESOURCE_EXHAUSTED"))
        )
        with client() as calendar, pytest.raises(RetryableError) as caught:
            calendar.request("POST", "/calendars", json_body={"summary": "Tokyo"})
        assert route.called
    assert MARKER not in str(caught.value)


def test_not_found_is_distinguishable_from_any_other_failure() -> None:
    with respx.mock(base_url=CALENDAR_API_BASE) as mock:
        route = mock.delete("/calendars/primary/events/gone").mock(
            return_value=httpx.Response(404, json=error_body(404, "NOT_FOUND"))
        )
        with client() as calendar, pytest.raises(CalendarNotFound) as caught:
            calendar.request("DELETE", "/calendars/primary/events/gone")
        assert route.called
    assert isinstance(caught.value, ToolError)
    assert not isinstance(caught.value, RetryableError)
    assert "NOT_FOUND" in str(caught.value)
    assert MARKER not in str(caught.value)


def test_a_transport_failure_is_retryable(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    with respx.mock(base_url=CALENDAR_API_BASE) as mock:
        route = mock.get("/calendars/one").mock(side_effect=httpx.ConnectError("no route to host"))
        with client() as calendar, pytest.raises(RetryableError):
            calendar.request("GET", "/calendars/one")
        assert route.called
    assert TOKEN not in caplog.text


def test_a_timeout_is_retryable() -> None:
    with respx.mock(base_url=CALENDAR_API_BASE) as mock:
        route = mock.get("/calendars/one").mock(side_effect=httpx.ReadTimeout("too slow"))
        with client() as calendar, pytest.raises(RetryableError):
            calendar.request("GET", "/calendars/one")
        assert route.called


def test_the_bearer_token_is_sent_and_never_surfaces(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    with respx.mock(base_url=CALENDAR_API_BASE) as mock:
        ok = mock.get("/calendars/one").mock(return_value=httpx.Response(200, json={"id": "cal-1"}))
        refused = mock.get("/calendars/two").mock(
            return_value=httpx.Response(400, json=error_body(400, "INVALID_ARGUMENT"))
        )
        with client() as calendar:
            assert calendar.request("GET", "/calendars/one") == {"id": "cal-1"}
            with pytest.raises(ToolError) as caught:
                calendar.request("GET", "/calendars/two")
        assert ok.called and refused.called
        assert mock.calls.call_count == 2
        assert ok.calls.last.request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in str(caught.value)
    assert TOKEN not in caplog.text


def test_an_empty_body_decodes_to_an_empty_mapping() -> None:
    with respx.mock(base_url=CALENDAR_API_BASE) as mock:
        route = mock.delete("/calendars/primary/events/one").mock(return_value=httpx.Response(204))
        with client() as calendar:
            assert calendar.request("DELETE", "/calendars/primary/events/one") == {}
        assert route.called
