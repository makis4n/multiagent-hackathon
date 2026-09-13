"""C1: the first draft. One model call with a flat schema; the code turns it into contract types.

`draft` takes the completion function as an argument so a test can hand in a recorded stand-in.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from trip_core.fakes import category_for
from trip_core.models import Day, Itinerary, Signal, Stop, TripBrief

CATEGORIES = ("food", "sight", "museum", "walk", "nightlife", "shopping", "nature", "rest")
MAX_SIGNALS = 40
SYSTEM = (
    "You plan city trips from what people posted recently. You only propose places that appear in the signals "
    "you are given, you cite the signal ids, and you answer with JSON that matches the schema exactly."
)
Complete = Callable[..., Any]


class DraftStop(BaseModel):
    day: int = Field(description="0-based index into the trip days listed in the prompt")
    start: str = Field(description='24h clock like "10:00"')
    end: str = Field(description='24h clock like "12:00"')
    place_name: str = Field(description="a name Google Maps would find, exactly as written in the signal")
    category: str = Field(description="one of food, sight, museum, walk, nightlife, shopping, nature, rest")
    why: str = Field(description="one sentence naming what the signal said")
    signal_ids: list[str]


class DraftItinerary(BaseModel):
    stops: list[DraftStop]
    notes: str = Field(default="", description="one sentence on the shape of the trip")


def draft(brief: TripBrief, signals: list[Signal], complete: Complete, *, model: str) -> Itinerary:
    """The prompt carries the best MAX_SIGNALS signals; the ids it cites are checked against all of them."""
    top = sorted(signals, key=lambda signal: signal.score, reverse=True)[:MAX_SIGNALS]
    result: DraftItinerary = complete(
        draft_prompt(brief, top), DraftItinerary, model=model, system=SYSTEM, temperature=0.3
    )
    return to_itinerary(brief, signals, result)


def draft_prompt(brief: TripBrief, signals: list[Signal]) -> str:
    days = "\n".join(f"  {index} = {date:%a %d %b %Y}" for index, date in enumerate(brief.dates))
    answers = "\n".join(f"  {question}: {answer}" for question, answer in brief.answers.items()) or "  none yet"
    lines = "\n".join(
        f"  {signal.id} | {signal.source.value} | {signal.posted_at:%Y-%m-%d} | {signal.title} | "
        f"{', '.join(signal.places_mentioned)}"
        if signal.posted_at
        else f"  {signal.id} | {signal.source.value} | undated | {signal.title} | {', '.join(signal.places_mentioned)}"
        for signal in signals
    )
    return (
        f"Trip: {brief.destination}, flying from {brief.origin}, {len(brief.dates)} days, "
        f"{brief.travellers} travellers, budget {brief.budget_band.value}, "
        f"styles: {', '.join(brief.styles) or 'any'}.\n"
        f"Day indexes:\n{days}\n"
        f"Answers so far:\n{answers}\n"
        f"Signals (id | source | posted | title | places):\n{lines}\n\n"
        f"Plan three or four stops per day between 10:00 and 21:00 with no overlaps and time to move between them. "
        f"Every stop is a real, specific place inside {brief.destination} (a venue, market, museum, park, street "
        f"or neighbourhood), named in a signal, listing that signal's id. Never another city or region, never a "
        f"fragment that is not a place name (ignore names like 'TOKYO MAP', 'Source' or a possessive). Never use "
        f"a place twice; write place_name so Google Maps finds it. Spread the styles across the days, put food "
        f"stops at meal times, and respect every answer above. category is one of: " + ", ".join(CATEGORIES) + "."
    )


def to_itinerary(brief: TripBrief, signals: list[Signal], draft: DraftItinerary) -> Itinerary:
    """Drops stops on days that do not exist, repairs unparseable times, keeps only signal ids that exist."""
    known = {signal.id for signal in signals}
    days = [Day(date=date) for date in brief.dates]
    ordered = sorted(draft.stops, key=lambda stop: (stop.day, parse_time(stop.start) or dt.time(10, 0)))
    for index, stop in enumerate(ordered):
        if not 0 <= stop.day < len(days) or not stop.place_name.strip():
            continue
        start = parse_time(stop.start) or dt.time(10, 0)
        end = parse_time(stop.end) or dt.time(0, 0)
        if end <= start:
            end = (dt.datetime.combine(dt.date.today(), start) + dt.timedelta(hours=2)).time()
        category = stop.category.strip().lower()
        days[stop.day].stops.append(
            Stop(
                id=f"stop-{index:02d}",
                day=stop.day,
                start=start,
                end=end,
                place_name=stop.place_name.strip(),
                category=category if category in CATEGORIES else category_for(stop.place_name),
                why=stop.why.strip() or "Suggested by the planner.",
                signal_ids=[signal_id for signal_id in stop.signal_ids if signal_id in known],
            )
        )
    return Itinerary(id=f"it-{brief.id}", brief_id=brief.id, days=days, notes=draft.notes.strip())


def parse_time(text: str) -> dt.time | None:
    for pattern in ("%H:%M", "%H.%M", "%H%M", "%H"):
        try:
            return dt.datetime.strptime(text.strip(), pattern).time()
        except ValueError:
            continue
    return None
