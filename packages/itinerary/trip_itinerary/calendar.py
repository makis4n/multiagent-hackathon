"""The transport to the Google Calendar API v3. It knows about HTTP and status codes, not about trips.

Plain `httpx` rather than the Google API client library, so every call can be recorded with `respx`. The bearer
token comes from a `TokenProvider`, read once per request so a refreshed token is picked up. Nothing here logs
the token, a request body or a response body: a failure carries the status code and the Google error status
string only.

Status mapping, from the Calendar API error guide and the Google HTTP/JSON error model:
429 and 5xx are `RetryableError`, 401 and 403 are `ToolError` asking for re-authorisation, 404 is
`CalendarNotFound` so a caller deleting something can treat it as already gone, everything else is `ToolError`.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from collections.abc import Mapping
from types import TracebackType
from typing import Any
from urllib.parse import quote

import httpx

from trip_core.models import Itinerary, RetryableError, Stop, ToolError, TripBrief
from trip_itinerary.credentials import TokenProvider

log = logging.getLogger(__name__)

CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
REQUEST_TIMEOUT_SECONDS = 20.0
CALENDAR_TIMEZONE_ENV = "TRIP_CALENDAR_TIMEZONE"
DEFAULT_CALENDAR_TIMEZONE = "UTC"
CALENDAR_WEB_URL = "https://calendar.google.com/calendar/u/0/r?cid="
_UNKNOWN_STATUS = "unknown"


class CalendarNotFound(ToolError):
    """The resource is not there. A delete can treat this as already gone; anything else is a real failure."""


class CalendarExporter:
    """Creates the trip calendar now; later steps add events to this same calendar."""

    def __init__(self, client: CalendarClient, *, timezone: str | None = None) -> None:
        self._client = client
        self._timezone = (
            timezone if timezone is not None else os.environ.get(CALENDAR_TIMEZONE_ENV, DEFAULT_CALENDAR_TIMEZONE)
        )

    def export(self, itinerary: Itinerary, brief: TripBrief) -> str:
        """Create or find the named secondary calendar and return its Google Calendar web URL."""
        calendar_id = self._find_calendar_id(_calendar_name(brief))
        if calendar_id is None:
            created = self._client.request(
                "POST",
                "/calendars",
                json_body={"summary": _calendar_name(brief), "timeZone": self._timezone},
            )
            calendar_id = _calendar_id(created, "create calendar")
        self._insert_events(calendar_id, itinerary)
        return f"{CALENDAR_WEB_URL}{quote(calendar_id, safe='@')}"

    def _find_calendar_id(self, name: str) -> str | None:
        page_token: str | None = None
        while True:
            params = {"pageToken": page_token} if page_token is not None else None
            page = self._client.request("GET", "/users/me/calendarList", params=params)
            items: object = page.get("items", [])
            if not isinstance(items, list):
                raise ToolError("the Google Calendar API returned calendar list items that are not a list")
            for item in items:
                if isinstance(item, dict) and item.get("summary") == name:
                    return _calendar_id(item, "calendar list")
            next_token: object = page.get("nextPageToken")
            if next_token is None:
                return None
            if not isinstance(next_token, str) or not next_token:
                raise ToolError("the Google Calendar API returned an invalid calendar list page token")
            page_token = next_token

    def _insert_events(self, calendar_id: str, itinerary: Itinerary) -> None:
        path = f"/calendars/{quote(calendar_id, safe='')}/events"
        for day in itinerary.days:
            for stop in day.stops:
                self._client.request("POST", path, json_body=_event_body(day.date, stop, itinerary.id, self._timezone))


class CalendarClient:
    """One authorised HTTP conversation with the Calendar API. Calendar and event calls are built on `request`."""

    def __init__(
        self,
        tokens: TokenProvider,
        *,
        base_url: str = CALENDAR_API_BASE,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self._tokens = tokens
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(base_url=base_url, timeout=timeout)

    def __enter__(self) -> CalendarClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        params: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send one authorised request and return the decoded body, empty for a 204."""
        headers = {"Authorization": f"Bearer {self._tokens.token()}", "Accept": "application/json"}
        try:
            response = self._client.request(method, path, headers=headers, json=json_body, params=params)
        except httpx.TransportError as exc:
            log.debug("the Google Calendar API could not be reached", exc_info=True)
            raise RetryableError(f"the Google Calendar API could not be reached for {method} {path}") from exc
        if response.is_success:
            return _decode(response, method, path)
        raise _failure(response, method, path)


def _decode(response: httpx.Response, method: str, path: str) -> dict[str, Any]:
    if response.status_code == 204 or not response.content:
        return {}
    try:
        payload: object = response.json()
    except ValueError as exc:
        log.debug("the Google Calendar API returned a body that is not JSON", exc_info=True)
        raise ToolError(f"the Google Calendar API returned a body that is not JSON for {method} {path}") from exc
    if not isinstance(payload, dict):
        raise ToolError(f"the Google Calendar API returned a body that is not an object for {method} {path}")
    return payload


def _failure(response: httpx.Response, method: str, path: str) -> ToolError:
    code = response.status_code
    log.debug("the Google Calendar API returned %s for %s %s", code, method, path)
    if code == 429 or code >= 500:
        return RetryableError(f"the Google Calendar API returned {code} for {method} {path}; retry")
    if code in (401, 403):
        return ToolError(
            f"the Google Calendar API returned {code} for {method} {path}; re-authorise the trip agent with "
            "Google Calendar and run it again"
        )
    status = _error_status(response)
    if code == 404:
        return CalendarNotFound(f"the Google Calendar API returned 404 ({status}) for {method} {path}")
    return ToolError(f"the Google Calendar API returned {code} ({status}) for {method} {path}")


def _error_status(response: httpx.Response) -> str:
    """The enum string only. `error.status` in the Google error model, `error.errors[].reason` in Calendar's."""
    try:
        payload: object = response.json()
    except ValueError:
        return _UNKNOWN_STATUS
    if not isinstance(payload, dict):
        return _UNKNOWN_STATUS
    error: object = payload.get("error")
    if not isinstance(error, dict):
        return _UNKNOWN_STATUS
    status: object = error.get("status")
    if isinstance(status, str) and status:
        return status
    details: object = error.get("errors")
    if isinstance(details, list) and details:
        first: object = details[0]
        if isinstance(first, dict):
            reason: object = first.get("reason")
            if isinstance(reason, str) and reason:
                return reason
    return _UNKNOWN_STATUS


def _calendar_name(brief: TripBrief) -> str:
    return f"{brief.destination} {brief.start_date.isoformat()}"


def _calendar_id(calendar: Mapping[str, Any], source: str) -> str:
    calendar_id: object = calendar.get("id")
    if not isinstance(calendar_id, str) or not calendar_id:
        raise ToolError(f"the Google Calendar API returned a {source} without an id")
    return calendar_id


def _event_body(date: dt.date, stop: Stop, itinerary_id: str, timezone: str) -> dict[str, object]:
    return {
        "summary": stop.place_name,
        "description": f"{stop.why}\n\nItinerary: {itinerary_id}",
        "start": {"dateTime": _local_date_time(date, stop.start), "timeZone": timezone},
        "end": {"dateTime": _local_date_time(date, stop.end), "timeZone": timezone},
    }


def _local_date_time(date: dt.date, time: dt.time) -> str:
    return dt.datetime.combine(date, time).replace(tzinfo=None).isoformat()
