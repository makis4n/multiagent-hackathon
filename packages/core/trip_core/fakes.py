"""A deterministic, offline fake for every Protocol. The fixture trip runs end to end on these.

They also fix the behaviour a real implementation must keep: FakeBooking.order is idempotent and refuses an
unconfirmed order; FakeVerifier runs the four checks; FakePlanner patches, it never regenerates.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
import random
import re
import uuid
from dataclasses import dataclass

from trip_core.models import (
    MAX_QUESTIONS,
    MAX_TRANSIT_MINUTES,
    BookingKind,
    BookingOption,
    BookingOrder,
    BudgetBand,
    Check,
    CheckKind,
    Day,
    Itinerary,
    ItineraryPatch,
    OpeningRange,
    OrderStatus,
    Place,
    RetryableError,
    Signal,
    SignalSource,
    Stop,
    ToolError,
    TripBrief,
    VerificationReport,
    load_fixture,
)
from trip_core.tools import PlaceResolver

PLACE_NOUNS = [
    "Central Market",
    "Old Town Walk",
    "Art Museum",
    "Riverside Cafe",
    "Night Market",
    "Botanical Garden",
    "Design District",
    "Harbour Viewpoint",
    "Noodle Alley",
    "Craft Beer Hall",
    "Contemporary Gallery",
    "Sunday Flea Market",
    "Rooftop Bar",
    "Book Street",
    "Vintage Arcade",
    "Bakery Row",
]
CATEGORY_BY_WORD = {
    "market": "food",
    "cafe": "food",
    "noodle": "food",
    "bakery": "food",
    "beer": "nightlife",
    "bar": "nightlife",
    "museum": "museum",
    "gallery": "museum",
    "garden": "nature",
    "valley": "nature",
    "walk": "walk",
    "district": "walk",
    "street": "walk",
    "viewpoint": "sight",
    "sky": "sight",
    "arcade": "shopping",
}
SLOTS = [(dt.time(10, 0), dt.time(12, 0)), (dt.time(13, 0), dt.time(15, 0)), (dt.time(16, 0), dt.time(18, 0))]
EVERY_DAY = {weekday: [OpeningRange(open=dt.time(9, 0), close=dt.time(21, 0))] for weekday in range(7)}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def category_for(place_name: str) -> str:
    lowered = place_name.lower()
    for word, category in CATEGORY_BY_WORD.items():
        if word in lowered:
            return category
    return "sight"


def distinct_places(signals: list[Signal]) -> list[str]:
    """Every place mentioned, once, best-scored signal first."""
    places: list[str] = []
    for signal in sorted(signals, key=lambda signal: signal.score, reverse=True):
        for place in signal.places_mentioned:
            if place not in places:
                places.append(place)
    return places


def skipped_places(brief: TripBrief) -> set[str]:
    """Answers shaped `skip: <place>` name places the traveller does not want."""
    return {answer[5:].strip().lower() for answer in brief.answers.values() if answer.lower().startswith("skip:")}


class FakeResearch:
    """16 signals over 16 places, deterministic per destination. Fixture signals win for their destination."""

    name = "fake"

    def __init__(self, fixture_signals: list[Signal] | None = None, fixture_destination: str | None = None):
        self.fixture_signals = fixture_signals or []
        self.fixture_destination = fixture_destination

    def search(self, brief: TripBrief) -> list[Signal]:
        if self.fixture_signals and brief.destination == self.fixture_destination:
            return list(self.fixture_signals)
        rng = random.Random(brief.destination)
        signals: list[Signal] = []
        for index in range(16):
            place = f"{brief.destination} {PLACE_NOUNS[index % len(PLACE_NOUNS)]}"
            source = SignalSource.reddit if index % 2 == 0 else SignalSource.youtube
            days_ago = 7 * index + rng.randint(0, 6)
            signals.append(
                Signal(
                    id=f"sig-{index:02d}",
                    source=source,
                    url=f"https://{source}.example/{slug(brief.destination)}/{index}",
                    title=f"{place}: still worth it in {brief.start_date.year}?",
                    excerpt=f"Went last month, {place} was the highlight. Go early.",
                    places_mentioned=[place],
                    posted_at=dt.datetime.combine(brief.start_date, dt.time(12, 0)) - dt.timedelta(days=days_ago),
                    score=round(1 - index * 0.04, 2),
                )
            )
        return signals


def _unit(text: str, salt: int) -> float:
    digest = hashlib.sha256(f"{salt}:{text}".encode()).digest()
    return int.from_bytes(digest[:4], "big") / 2**32


def _hours_for(name: str) -> dict[int, list[OpeningRange]]:
    if "(closed)" in name.lower():
        return {6: [OpeningRange(open=dt.time(0, 0), close=dt.time(1, 0))]}
    return EVERY_DAY


class FakePlaceResolver:
    """Coordinates from a hash, so distances are stable. A name containing "(closed)" gets hours that never
    match the plan; a name containing "nowhere" does not resolve. Both exist so the failure path runs on fakes."""

    def __init__(self) -> None:
        self.places: dict[str, Place] = {}

    def resolve(self, name: str, near: str) -> Place | None:
        if "nowhere" in name.lower():
            return None
        place_id = f"fake:{slug(name)}"
        if place_id not in self.places:
            self.places[place_id] = Place(
                id=place_id,
                name=name,
                address=f"{name}, {near}",
                lat=_unit(near, 0) * 120 - 60 + _unit(name, 1) * 0.02,
                lng=_unit(near, 2) * 360 - 180 + _unit(name, 3) * 0.02,
                opening_hours=_hours_for(name),
                rating=4.4,
            )
        return self.places[place_id]

    def get(self, place_id: str) -> Place | None:
        return self.places.get(place_id)


def _stop(stop_id: str, day: int, start: dt.time, end: dt.time, place: str, signals: list[Signal]) -> Stop:
    backing = [signal for signal in signals if place in signal.places_mentioned]
    return Stop(
        id=stop_id,
        day=day,
        start=start,
        end=end,
        place_name=place,
        category=category_for(place),
        why=f"Mentioned in: {backing[0].title}" if backing else "No signal behind it.",
        signal_ids=[signal.id for signal in backing],
    )


class FakePlanner:
    """Three stops a day from the signal places, one deliberately closed venue on day 0, patches on `skip:`."""

    def draft(self, brief: TripBrief, signals: list[Signal]) -> Itinerary:
        places = distinct_places(signals) or [f"{brief.destination} Old Town Walk"]
        days: list[Day] = []
        counter = 0
        for day_index, date in enumerate(brief.dates):
            stops: list[Stop] = []
            for slot_index, (start, end) in enumerate(SLOTS):
                place = places[(day_index * len(SLOTS) + slot_index) % len(places)]
                stops.append(_stop(f"stop-{counter:02d}", day_index, start, end, place, signals))
                counter += 1
            days.append(Day(date=date, stops=stops))
        days[0].stops.append(
            Stop(
                id="stop-closed",
                day=0,
                start=dt.time(19, 0),
                end=dt.time(21, 0),
                place_name=f"{brief.destination} Pop-up (closed)",
                category="food",
                why="Looked good on a listicle; no signal behind it.",
            )
        )
        return Itinerary(id=f"it-{brief.id}", brief_id=brief.id, days=days, notes="fake draft")

    def questions(self, brief: TripBrief, itinerary: Itinerary) -> list[str]:
        candidates = [
            "Anything to skip?",
            "Slow mornings or packed days?",
            "Any food you avoid?",
            "Is a lot of walking fine?",
        ]
        return [question for question in candidates if question not in brief.answers][:MAX_QUESTIONS]

    def refine(
        self, brief: TripBrief, itinerary: Itinerary, answers: dict[str, str], signals: list[Signal]
    ) -> list[ItineraryPatch]:
        wanted = {answer[5:].strip().lower() for answer in answers.values() if answer.lower().startswith("skip:")}
        return [
            ItineraryPatch(op="remove", stop_id=stop.id)
            for stop in itinerary.stops()
            if stop.place_name.lower() in wanted
        ]

    def replace_failed(
        self, brief: TripBrief, itinerary: Itinerary, report: VerificationReport, signals: list[Signal]
    ) -> list[ItineraryPatch]:
        used = {stop.place_name for stop in itinerary.stops()}
        skipped = skipped_places(brief)
        spare = [place for place in distinct_places(signals) if place not in used and place.lower() not in skipped]
        patches: list[ItineraryPatch] = []
        for stop_id in report.failed_stop_ids():
            day_index, stop_index = itinerary.locate(stop_id)
            old = itinerary.days[day_index].stops[stop_index]
            if spare:
                replacement = _stop(f"{stop_id}-r", day_index, old.start, old.end, spare.pop(0), signals)
                patches.append(ItineraryPatch(op="replace", stop_id=stop_id, stop=replacement))
            else:
                patches.append(ItineraryPatch(op="remove", stop_id=stop_id))
        return patches


def haversine_km(a: Place, b: Place) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (a.lat, a.lng, b.lat, b.lng))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def travel_minutes(a: Place, b: Place, speed_kmh: float = 15.0) -> int:
    return math.ceil(haversine_km(a, b) / speed_kmh * 60) + 5


class FakeVerifier:
    """The four checks over the resolver's places, straight-line travel time at 15 km/h. Lane C keeps the
    checks and swaps the travel time for the Routes API."""

    def __init__(self, resolver: PlaceResolver) -> None:
        self.resolver = resolver

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
                    minutes = travel_minutes(previous, place)
                    checks.append(
                        Check(
                            stop_id=stop.id,
                            check=CheckKind.reachable,
                            ok=minutes <= MAX_TRANSIT_MINUTES,
                            detail=f"{minutes} min from {previous.name}",
                        )
                    )
                previous = place
        return VerificationReport(itinerary_id=itinerary.id, checks=checks)


class FakeBooking:
    """Idempotent by key. `fail_once` holds keys whose first `order` records the order and then raises
    RetryableError, the way a provider that created the order but lost the response behaves."""

    name = "fake"

    def __init__(self) -> None:
        self.orders: dict[str, BookingOrder] = {}
        self.fail_once: set[str] = set()
        self.order_calls = 0

    def search(self, brief: TripBrief, kind: BookingKind) -> list[BookingOption]:
        factor = {BudgetBand.low: 1, BudgetBand.mid: 2, BudgetBand.high: 4}[brief.budget_band]
        if kind == BookingKind.flight:
            return [
                BookingOption(
                    kind=kind,
                    provider=self.name,
                    provider_ref=f"off_{slug(brief.origin)}_{slug(brief.destination)}",
                    title=f"{brief.origin} to {brief.destination}, return, {brief.travellers} pax",
                    price_minor=factor * 45_000 * brief.travellers,
                    details={"depart": brief.start_date.isoformat(), "return": brief.end_date.isoformat()},
                )
            ]
        if kind == BookingKind.stay:
            return [
                BookingOption(
                    kind=kind,
                    provider=self.name,
                    provider_ref=f"stay_{slug(brief.destination)}",
                    title=f"{brief.nights} nights near {brief.destination} Central Market",
                    price_minor=factor * 9_000 * brief.nights,
                    details={"check_in": brief.start_date.isoformat(), "check_out": brief.end_date.isoformat()},
                )
            ]
        return []

    def order(self, option: BookingOption, idempotency_key: str, confirmed_by_user_at: dt.datetime) -> BookingOrder:
        self.order_calls += 1
        if confirmed_by_user_at is None:  # a runtime guard for callers that ignore the type
            raise ToolError("refusing an order without confirmed_by_user_at")
        existing = self.orders.get(idempotency_key)
        if existing is not None:
            return existing
        order = BookingOrder(
            id=f"ord_{uuid.uuid5(uuid.NAMESPACE_URL, idempotency_key).hex[:10]}",
            option=option,
            idempotency_key=idempotency_key,
            confirmed_by_user_at=confirmed_by_user_at,
            status=OrderStatus.confirmed,
            provider_order_id=f"FAKE-{idempotency_key[:6].upper()}",
            receipt={"total_minor": option.price_minor, "currency": option.currency},
        )
        self.orders[idempotency_key] = order
        if idempotency_key in self.fail_once:
            self.fail_once.discard(idempotency_key)
            raise RetryableError("provider returned 502 after creating the order")
        return order


class FakeCalendar:
    def export(self, itinerary: Itinerary, brief: TripBrief) -> str:
        return f"https://calendar.example/{slug(brief.destination)}/{itinerary.id}/v{itinerary.version}"


@dataclass
class FakeSet:
    research: list[FakeResearch]
    resolver: FakePlaceResolver
    planner: FakePlanner
    verifier: FakeVerifier
    booking: FakeBooking
    calendar: FakeCalendar


def default_fakes() -> FakeSet:
    fixture = load_fixture("tokyo")
    resolver = FakePlaceResolver()
    return FakeSet(
        research=[FakeResearch(fixture.signals, fixture.brief.destination)],
        resolver=resolver,
        planner=FakePlanner(),
        verifier=FakeVerifier(resolver),
        booking=FakeBooking(),
        calendar=FakeCalendar(),
    )
