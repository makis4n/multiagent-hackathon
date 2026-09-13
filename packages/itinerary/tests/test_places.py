"""Unit tests on the documented response shapes, plus recorded calls (RECORD=1 uv run --env-file .env pytest
packages/itinerary) that replay offline once the cassettes exist."""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import httpx
import pytest

from trip_core.cassette import cassette
from trip_core.models import Day, Itinerary, Place, Stop
from trip_itinerary.places import GooglePlaces, parse_place
from trip_itinerary.verifier import RoutesTravel, RoutesVerifier, parse_duration_minutes

CASSETTES = Path(__file__).parent / "cassettes"

SAMPLE_PLACE = {
    "id": "ChIJ_tsukiji",
    "displayName": {"text": "Tsukiji Outer Market", "languageCode": "en"},
    "formattedAddress": "4 Chome Tsukiji, Chuo City, Tokyo",
    "location": {"latitude": 35.6654, "longitude": 139.7707},
    "rating": 4.3,
    "priceLevel": "PRICE_LEVEL_MODERATE",
    "regularOpeningHours": {
        "periods": [
            {"open": {"day": 0, "hour": 9, "minute": 0}, "close": {"day": 0, "hour": 14, "minute": 0}},
            {"open": {"day": 1, "hour": 7, "minute": 0}, "close": {"day": 1, "hour": 15, "minute": 0}},
            {"open": {"day": 5, "hour": 18, "minute": 0}, "close": {"day": 6, "hour": 2, "minute": 0}},
        ]
    },
}


def test_parse_place_maps_google_weekdays_onto_the_contract() -> None:
    place = parse_place(SAMPLE_PLACE)
    assert place.id == "ChIJ_tsukiji" and place.name == "Tsukiji Outer Market"
    assert place.price_level == 2 and place.rating == 4.3
    assert sorted(place.opening_hours) == [0, 4, 6]  # Google Mon=1 -> 0, Fri=5 -> 4, Sun=0 -> 6
    sunday, monday, friday = dt.date(2026, 11, 15), dt.date(2026, 11, 16), dt.date(2026, 11, 13)
    assert place.is_open(sunday, dt.time(10, 0)) is True
    assert place.is_open(monday, dt.time(7, 30)) is True
    assert place.is_open(monday, dt.time(16, 0)) is False
    assert place.is_open(friday, dt.time(23, 0)) is True  # closes past midnight: open until 23:59 that day
    assert place.is_open(dt.date(2026, 11, 12), dt.time(10, 0)) is False  # Thursday: no period


def test_parse_place_open_24_hours_means_every_day() -> None:
    place = parse_place(
        {
            "id": "y",
            "displayName": {"text": "Omoide Yokocho"},
            "location": {"latitude": 35.69, "longitude": 139.70},
            "regularOpeningHours": {"periods": [{"open": {"day": 0, "hour": 0, "minute": 0}}]},
        }
    )
    assert sorted(place.opening_hours) == list(range(7))
    assert place.is_open(dt.date(2026, 11, 12), dt.time(19, 0)) is True  # a Thursday evening


def test_parse_place_without_hours_is_unknown_not_closed() -> None:
    place = parse_place({"id": "x", "displayName": {"text": "X"}, "location": {"latitude": 1, "longitude": 2}})
    assert place.opening_hours == {}
    assert place.is_open(dt.date(2026, 11, 12), dt.time(10, 0)) is None


def _client_with_photo(photo_status: int) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/media"):
            assert request.url.params["skipHttpRedirect"] == "true"
            return httpx.Response(photo_status, json={"photoUri": "https://lh3.googleusercontent.com/p/abc"})
        found = dict(SAMPLE_PLACE, photos=[{"name": "places/ChIJ_tsukiji/photos/xyz", "widthPx": 4000}])
        return httpx.Response(200, json={"places": [found]})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_resolve_attaches_the_first_photo_as_a_public_url() -> None:
    place = GooglePlaces("k", client=_client_with_photo(200)).resolve("Tsukiji Outer Market", "Tokyo")
    assert place is not None and place.photo_url == "https://lh3.googleusercontent.com/p/abc"


def test_a_failed_photo_lookup_leaves_the_place_without_one() -> None:
    place = GooglePlaces("k", client=_client_with_photo(500)).resolve("Tsukiji Outer Market", "Tokyo")
    assert place is not None and place.photo_url is None and place.name == "Tsukiji Outer Market"


def test_parse_duration() -> None:
    assert parse_duration_minutes({"routes": [{"duration": "1234s"}]}) == 21
    assert parse_duration_minutes({"routes": [{"duration": "59.5s"}]}) == 1
    assert parse_duration_minutes({}) is None


def test_verifier_falls_back_to_straight_line_when_routes_fails() -> None:
    a = Place(id="a", name="A", lat=35.66, lng=139.77)
    b = Place(id="b", name="B", lat=35.67, lng=139.78)

    class Resolver:
        def resolve(self, name: str, near: str) -> Place | None:
            return None

        def get(self, place_id: str) -> Place | None:
            return {"a": a, "b": b}.get(place_id)

    def broken_travel(origin: Place, destination: Place) -> tuple[int, str]:
        from trip_core.models import ToolError

        raise ToolError("routes 400: bad request")

    itinerary = Itinerary(
        id="it",
        brief_id="b",
        days=[
            Day(
                date=dt.date(2026, 11, 12),
                stops=[
                    Stop(
                        id="s1",
                        day=0,
                        start=dt.time(10),
                        end=dt.time(12),
                        place_name="A",
                        place_id="a",
                        category="sight",
                        why="",
                    ),
                    Stop(
                        id="s2",
                        day=0,
                        start=dt.time(13),
                        end=dt.time(15),
                        place_name="B",
                        place_id="b",
                        category="sight",
                        why="",
                    ),
                ],
            )
        ],
    )
    report = RoutesVerifier(Resolver(), broken_travel).verify(itinerary)
    reachable = [check for check in report.checks if check.check == "reachable"]
    assert len(reachable) == 1 and reachable[0].ok and "straight-line estimate" in reachable[0].detail
    assert report.passed


def recorded_places_client(name: str) -> httpx.Client:
    """An httpx client whose responses come from a cassette; RECORD=1 makes real calls and saves them."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        path = CASSETTES / f"{name}_{calls['n']:02d}.json"

        def fetch() -> dict:
            live = httpx.Client(timeout=15.0).send(request)
            return {"status": live.status_code, "json": live.json()}

        saved = cassette(path, fetch)
        return httpx.Response(saved["status"], json=saved["json"], request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


needs_cassette = pytest.mark.skipif(
    not (CASSETTES / "places_01.json").exists() and os.environ.get("RECORD") != "1",
    reason="record with RECORD=1 and GOOGLE_MAPS_API_KEY first",
)


@needs_cassette
def test_recorded_mori_art_museum_resolves_with_hours() -> None:
    resolver = GooglePlaces(os.environ.get("GOOGLE_MAPS_API_KEY", "recorded"), client=recorded_places_client("places"))
    place = resolver.resolve("Mori Art Museum", "Tokyo")
    assert place is not None and "Mori Art Museum" in place.name
    assert 35.6 < place.lat < 35.7
    assert place.is_open(dt.date(2026, 11, 12), dt.time(15, 0)) is True  # Thursday 15:00
    assert place.is_open(dt.date(2026, 11, 17), dt.time(20, 0)) is False  # Tuesday closes 17:00
    assert resolver.get(place.id) is place


@needs_cassette
def test_recorded_transit_between_two_tokyo_places() -> None:
    travel = RoutesTravel(os.environ.get("GOOGLE_MAPS_API_KEY", "recorded"), client=recorded_places_client("routes"))
    tsukiji = Place(id="t", name="Tsukiji", lat=35.6654, lng=139.7707)
    teamlab = Place(id="p", name="teamLab Planets", lat=35.6491, lng=139.7897)
    minutes, how = travel(tsukiji, teamlab)
    assert 5 <= minutes <= 60
    assert how in ("transit", "drive-based estimate, no transit route")
