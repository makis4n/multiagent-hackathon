"""C2: the Verifier. The four checks from the fake, with transit times from the Routes API and a straight-line
fallback that says so in the check detail."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from typing import Any

import httpx

from trip_core.fakes import travel_minutes as straight_line_minutes
from trip_core.models import (
    MAX_TRANSIT_MINUTES,
    Check,
    CheckKind,
    Itinerary,
    Place,
    RetryableError,
    ToolError,
    VerificationReport,
)
from trip_core.tools import PlaceResolver

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
RETRYABLE = {408, 429, 500, 502, 503, 504}
DRIVE_TO_TRANSIT = 1.2
TRANSFER_MINUTES = 5

Travel = Callable[[Place, Place], tuple[int, str]]


class RoutesTravel:
    """Transit minutes between two places via Routes API computeRoutes, cached per pair."""

    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=10.0)
        self.cache: dict[tuple[str, str], tuple[int, str]] = {}

    def __call__(self, origin: Place, destination: Place) -> tuple[int, str]:
        key = (origin.id, destination.id)
        if key not in self.cache:
            self.cache[key] = self._compute(origin, destination)
        return self.cache[key]

    def _compute(self, origin: Place, destination: Place) -> tuple[int, str]:
        """Transit when Google has a route; otherwise driving time times 1.2 plus a transfer buffer, a rough
        stand-in for city transit under a 45-minute cap; straight line only when both fail."""
        transit = self._route(origin, destination, "TRANSIT")
        if transit is not None:
            return transit, "transit"
        drive = self._route(origin, destination, "DRIVE")
        if drive is not None:
            return math.ceil(drive * DRIVE_TO_TRANSIT) + TRANSFER_MINUTES, "drive-based estimate, no transit route"
        return straight_line_minutes(origin, destination), "no route, straight-line estimate"

    def _route(self, origin: Place, destination: Place, mode: str) -> int | None:
        body = {
            "origin": {"location": {"latLng": {"latitude": origin.lat, "longitude": origin.lng}}},
            "destination": {"location": {"latLng": {"latitude": destination.lat, "longitude": destination.lng}}},
            "travelMode": mode,
        }
        headers = {
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "routes.duration,routes.distanceMeters",
            "Content-Type": "application/json",
        }
        try:
            response = self.client.post(ROUTES_URL, headers=headers, json=body)
        except httpx.HTTPError as error:
            raise RetryableError(f"routes: {type(error).__name__}") from error
        if response.status_code in RETRYABLE:
            raise RetryableError(f"routes {response.status_code}: {response.text[:200]}")
        if response.status_code >= 400:
            raise ToolError(f"routes {response.status_code}: {response.text[:200]}")
        return parse_duration_minutes(response.json())


def parse_duration_minutes(data: dict[str, Any]) -> int | None:
    routes = data.get("routes") or []
    if not routes:
        return None
    match = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(routes[0].get("duration", "")))
    return math.ceil(float(match.group(1)) / 60) if match else None


class RoutesVerifier:
    def __init__(self, resolver: PlaceResolver, travel: Travel) -> None:
        self.resolver = resolver
        self.travel = travel

    def verify(self, itinerary: Itinerary) -> VerificationReport:
        checks: list[Check] = []
        for day_index, day in enumerate(itinerary.days):
            previous: Place | None = None
            for stop in day.stops:
                place = self.resolver.get(stop.place_id) if stop.place_id else None
                checks.append(
                    Check(
                        stop_id=stop.id,
                        check=CheckKind.exists,
                        ok=place is not None,
                        detail="" if place else f"{stop.place_name!r} did not resolve",
                    )
                )
                in_window = stop.day == day_index and stop.start < stop.end
                checks.append(
                    Check(
                        stop_id=stop.id,
                        check=CheckKind.in_window,
                        ok=in_window,
                        detail="" if in_window else f"day {stop.day} / {stop.start}-{stop.end} is not in the plan",
                    )
                )
                if place is None:
                    previous = None
                    continue
                is_open = place.is_open(day.date, stop.start)
                checks.append(
                    Check(
                        stop_id=stop.id,
                        check=CheckKind.open,
                        ok=is_open is not False,
                        detail=(
                            "hours unknown"
                            if is_open is None
                            else ("" if is_open else f"closed at {stop.start:%H:%M} on {day.date:%A}")
                        ),
                    )
                )
                if previous is not None:
                    try:
                        minutes, how = self.travel(previous, place)
                    except ToolError as error:
                        minutes, how = straight_line_minutes(previous, place), f"straight-line estimate ({error})"
                    checks.append(
                        Check(
                            stop_id=stop.id,
                            check=CheckKind.reachable,
                            ok=minutes <= MAX_TRANSIT_MINUTES,
                            detail=f"{minutes} min from {previous.name} ({how})",
                        )
                    )
                previous = place
        return VerificationReport(itinerary_id=itinerary.id, checks=checks)
