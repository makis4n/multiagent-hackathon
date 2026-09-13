"""C2: the PlaceResolver on Google Places API (New). One text search per stop name, cached by place id."""

from __future__ import annotations

import datetime as dt
from typing import Any

import httpx

from trip_core.models import OpeningRange, Place, RetryableError, ToolError

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
FIELDS = ["id", "displayName", "formattedAddress", "location", "regularOpeningHours", "rating", "priceLevel"]
PRICE_LEVELS = {
    "PRICE_LEVEL_FREE": 0,
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}
RETRYABLE = {408, 429, 500, 502, 503, 504}


class GooglePlaces:
    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=10.0)
        self.places: dict[str, Place] = {}

    def resolve(self, name: str, near: str) -> Place | None:
        body = {"textQuery": f"{name}, {near}", "pageSize": 1}
        data = self._request("POST", SEARCH_URL, json=body, mask=",".join(f"places.{field}" for field in FIELDS))
        found = data.get("places") or []
        if not found:
            return None
        place = parse_place(found[0])
        self.places[place.id] = place
        return place

    def get(self, place_id: str) -> Place | None:
        cached = self.places.get(place_id)
        if cached is not None:
            return cached
        try:
            data = self._request("GET", DETAILS_URL.format(place_id=place_id), mask=",".join(FIELDS))
        except ToolError as error:
            if "404" in str(error):
                return None
            raise
        place = parse_place(data)
        self.places[place.id] = place
        return place

    def _request(self, method: str, url: str, *, mask: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": mask, "Content-Type": "application/json"}
        try:
            response = self.client.request(method, url, headers=headers, json=json)
        except httpx.HTTPError as error:
            raise RetryableError(f"places: {type(error).__name__}") from error
        if response.status_code in RETRYABLE:
            raise RetryableError(f"places {response.status_code}: {response.text[:200]}")
        if response.status_code >= 400:
            raise ToolError(f"places {response.status_code}: {response.text[:200]}")
        return response.json()


def parse_place(data: dict[str, Any]) -> Place:
    """Google counts weekdays from Sunday = 0; the contract counts from Monday = 0."""
    hours: dict[int, list[OpeningRange]] = {}
    for period in (data.get("regularOpeningHours") or {}).get("periods") or []:
        opening = period.get("open") or {}
        closing = period.get("close")
        if "day" not in opening:
            continue
        weekday = (int(opening["day"]) - 1) % 7
        start = dt.time(int(opening.get("hour", 0)), int(opening.get("minute", 0)))
        if closing is None:
            end = dt.time(23, 59)
        elif int(closing.get("day", opening["day"])) != int(opening["day"]):
            end = dt.time(23, 59)
        else:
            end = dt.time(int(closing.get("hour", 0)), int(closing.get("minute", 0)))
        hours.setdefault(weekday, []).append(OpeningRange(open=start, close=end))
    location = data.get("location") or {}
    return Place(
        id=data["id"],
        name=(data.get("displayName") or {}).get("text", ""),
        address=data.get("formattedAddress", ""),
        lat=float(location.get("latitude", 0.0)),
        lng=float(location.get("longitude", 0.0)),
        opening_hours=hours,
        rating=data.get("rating"),
        price_level=PRICE_LEVELS.get(data.get("priceLevel", ""), None),
    )
