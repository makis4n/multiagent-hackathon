"""The contract. Every lane produces or consumes these types; nothing else crosses a package boundary.

Additive changes only after milestone 1. Announce every change in the team chat as `<lane>: CONTRACT — <what>`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

MAX_TRANSIT_MINUTES = 45
MAX_QUESTIONS = 4
FIXTURES = Path(__file__).parent / "fixtures"


class BudgetBand(StrEnum):
    low = "low"
    mid = "mid"
    high = "high"


class TripBrief(BaseModel):
    """What the traveller told us. `answers` fills up during the refinement round."""

    id: str
    destination: str
    origin: str = Field(description="where the traveller flies from: an IATA airport or city code, e.g. ARN")
    destination_code: str | None = Field(
        default=None, description="IATA airport or city code for the destination, e.g. TYO; booking uses it"
    )
    start_date: dt.date
    end_date: dt.date
    travellers: int = 2
    budget_band: BudgetBand = BudgetBand.mid
    styles: list[str] = Field(default_factory=list, description="food, art, nightlife, nature, family, ...")
    answers: dict[str, str] = Field(default_factory=dict, description="question -> answer")

    @model_validator(mode="after")
    def _dates_in_order(self) -> TripBrief:
        if self.end_date < self.start_date:
            raise ValueError("end_date is before start_date")
        return self

    @property
    def airports(self) -> tuple[str, str]:
        """(origin, destination) codes for a flight search; the destination code falls back to the name."""
        return self.origin.strip().upper(), (self.destination_code or self.destination).strip().upper()

    @property
    def nights(self) -> int:
        return (self.end_date - self.start_date).days

    @property
    def dates(self) -> list[dt.date]:
        return [self.start_date + dt.timedelta(days=offset) for offset in range(self.nights + 1)]


class SignalSource(StrEnum):
    reddit = "reddit"
    youtube = "youtube"
    web = "web"


class Signal(BaseModel):
    """One piece of evidence that a place or activity is worth it right now."""

    id: str
    source: SignalSource
    url: str
    title: str
    excerpt: str
    places_mentioned: list[str] = Field(default_factory=list)
    posted_at: dt.datetime | None = None
    score: float = Field(default=0.0, description="0..1, recency-weighted relevance; Lane B owns the formula")


class OpeningRange(BaseModel):
    open: dt.time
    close: dt.time


class Place(BaseModel):
    id: str = Field(description="Google place_id; fakes use fake:<slug>")
    name: str
    address: str = ""
    lat: float
    lng: float
    opening_hours: dict[int, list[OpeningRange]] = Field(
        default_factory=dict,
        description="weekday (0 = Monday) -> open ranges; a missing weekday is closed; an empty dict is unknown",
    )
    rating: float | None = None
    price_level: int | None = None
    photo_url: str | None = Field(default=None, description="a public image URL for the place, if the resolver has one")

    def is_open(self, on: dt.date, at: dt.time) -> bool | None:
        """True or False when hours are known, None when unknown."""
        if not self.opening_hours:
            return None
        return any(span.open <= at <= span.close for span in self.opening_hours.get(on.weekday(), []))


class StopStatus(StrEnum):
    draft = "draft"
    verified = "verified"
    failed = "failed"


class Stop(BaseModel):
    id: str
    day: int = Field(description="0-based index into Itinerary.days")
    start: dt.time
    end: dt.time
    place_name: str
    place_id: str | None = Field(default=None, description="set by the PlaceResolver; None until resolved")
    category: str = Field(description="food, sight, museum, walk, nightlife, shopping, nature, rest")
    why: str = Field(description="one sentence that says what the signals said")
    signal_ids: list[str] = Field(default_factory=list)
    status: StopStatus = StopStatus.draft
    failure_reason: str | None = None


class Day(BaseModel):
    date: dt.date
    stops: list[Stop] = Field(default_factory=list)


class Itinerary(BaseModel):
    id: str
    brief_id: str
    version: int = 1
    days: list[Day] = Field(default_factory=list)
    notes: str = ""

    def stops(self) -> list[Stop]:
        return [stop for day in self.days for stop in day.stops]

    def locate(self, stop_id: str) -> tuple[int, int]:
        for day_index, day in enumerate(self.days):
            for stop_index, stop in enumerate(day.stops):
                if stop.id == stop_id:
                    return day_index, stop_index
        raise KeyError(f"no stop {stop_id}")


class ItineraryPatch(BaseModel):
    """One edit. Refinement and replacement produce patches; the loop applies them. Never regenerate."""

    op: Literal["add", "remove", "move", "replace"]
    stop_id: str | None = Field(default=None, description="remove, move, replace: the stop to act on")
    stop: Stop | None = Field(default=None, description="add, replace: the new stop")
    target_day: int | None = Field(default=None, description="add, move: the day to put it in")
    position: int | None = Field(default=None, description="add, move: index within the day; None appends")


def apply_patch(itinerary: Itinerary, patch: ItineraryPatch) -> Itinerary:
    """Pure. Returns a new Itinerary with version + 1. Raises ValueError when the patch does not apply."""
    result = itinerary.model_copy(deep=True)
    if patch.op == "add":
        if patch.stop is None or patch.target_day is None:
            raise ValueError("add needs stop and target_day")
        _insert(result, patch.stop, patch.target_day, patch.position)
    elif patch.op == "remove":
        _pop(result, patch.stop_id)
    elif patch.op == "move":
        if patch.target_day is None:
            raise ValueError("move needs target_day")
        _insert(result, _pop(result, patch.stop_id), patch.target_day, patch.position)
    elif patch.op == "replace":
        if patch.stop is None:
            raise ValueError("replace needs stop")
        day_index, stop_index = result.locate(_require(patch.stop_id))
        result.days[day_index].stops[stop_index] = patch.stop.model_copy(update={"day": day_index})
    result.version += 1
    return result


def _require(stop_id: str | None) -> str:
    if stop_id is None:
        raise ValueError("stop_id is required")
    return stop_id


def _pop(itinerary: Itinerary, stop_id: str | None) -> Stop:
    day_index, stop_index = itinerary.locate(_require(stop_id))
    return itinerary.days[day_index].stops.pop(stop_index)


def _insert(itinerary: Itinerary, stop: Stop, target_day: int, position: int | None) -> None:
    if not 0 <= target_day < len(itinerary.days):
        raise ValueError(f"no day {target_day}")
    stops = itinerary.days[target_day].stops
    stops.insert(len(stops) if position is None else position, stop.model_copy(update={"day": target_day}))


class CheckKind(StrEnum):
    exists = "exists"
    open = "open"
    reachable = "reachable"
    in_window = "in_window"


class Check(BaseModel):
    stop_id: str
    check: CheckKind
    ok: bool
    detail: str = ""


class VerificationReport(BaseModel):
    itinerary_id: str
    checks: list[Check] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(check.ok for check in self.checks)

    def failed_stop_ids(self) -> list[str]:
        seen: list[str] = []
        for check in self.checks:
            if not check.ok and check.stop_id not in seen:
                seen.append(check.stop_id)
        return seen

    def pass_rate(self) -> float:
        stop_ids = {check.stop_id for check in self.checks}
        if not stop_ids:
            return 1.0
        return 1 - len(self.failed_stop_ids()) / len(stop_ids)


class BookingKind(StrEnum):
    flight = "flight"
    stay = "stay"
    activity = "activity"


class BookingOption(BaseModel):
    kind: BookingKind
    provider: str
    provider_ref: str = Field(description="the provider's own id for this offer")
    title: str
    price_minor: int
    currency: str = "EUR"
    details: dict[str, Any] = Field(default_factory=dict)


class OrderStatus(StrEnum):
    pending = "pending"
    confirmed = "confirmed"
    failed = "failed"


class BookingOrder(BaseModel):
    id: str
    option: BookingOption
    idempotency_key: str
    confirmed_by_user_at: dt.datetime
    status: OrderStatus
    provider_order_id: str | None = None
    receipt: dict[str, Any] = Field(default_factory=dict)


def idempotency_key(brief_id: str, option: BookingOption) -> str:
    raw = f"{brief_id}:{option.kind}:{option.provider}:{option.provider_ref}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


class Replacement(BaseModel):
    """A stop the verifier rejected and what took its place. `new` is None when it was removed."""

    old: Stop
    new: Stop | None
    reason: str


class TripState(BaseModel):
    """Everything the loop produced for one brief. The UI renders this; the evals score it."""

    brief: TripBrief
    signals: list[Signal] = Field(default_factory=list)
    itinerary: Itinerary | None = None
    questions: list[str] = Field(default_factory=list)
    places: dict[str, Place] = Field(default_factory=dict)
    report: VerificationReport | None = None
    replacements: list[Replacement] = Field(default_factory=list)
    options: list[BookingOption] = Field(default_factory=list)
    orders: list[BookingOrder] = Field(default_factory=list)
    calendar_url: str | None = None
    errors: list[str] = Field(default_factory=list)


class Fixture(BaseModel):
    brief: TripBrief
    signals: list[Signal] = Field(default_factory=list)


def load_fixture(name: str) -> Fixture:
    path = FIXTURES / f"{name}.json"
    if not path.exists():
        available = sorted(candidate.stem for candidate in FIXTURES.glob("*.json"))
        raise FileNotFoundError(f"no fixture {name}; available: {available}")
    return Fixture.model_validate(json.loads(path.read_text()))


class ToolError(Exception):
    """A tool failed in a way a retry will not fix."""


class RetryableError(ToolError):
    """A tool failed in a way one retry may fix: timeout, 5xx, rate limit."""
