"""C1: the Gemini planner. Draft and questions are model calls with flat schemas; the code turns them into
contract types. Refine and replace_failed keep the fake's rules until C3 puts the model behind them too."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from trip_core.fakes import FakePlanner, category_for
from trip_core.llm import complete_json, model_fast, model_main
from trip_core.models import (
    MAX_QUESTIONS,
    Day,
    Itinerary,
    ItineraryPatch,
    Signal,
    Stop,
    TripBrief,
    VerificationReport,
)

CATEGORIES = ("food", "sight", "museum", "walk", "nightlife", "shopping", "nature", "rest")
MAX_SIGNALS = 40
SYSTEM = (
    "You plan city trips from what people posted recently. You only propose places that appear in the signals "
    "you are given, you cite the signal ids, and you answer with JSON that matches the schema exactly."
)


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


class Questions(BaseModel):
    questions: list[str]


class ReplacementStop(BaseModel):
    place_name: str = Field(description="a real place inside the destination, named in a signal")
    category: str
    why: str
    signal_ids: list[str]


class ReplacementChoice(BaseModel):
    stop_id: str
    replacement: ReplacementStop | None = Field(default=None, description="None means remove the stop")


class Replacements(BaseModel):
    replacements: list[ReplacementChoice]


Complete = Callable[..., Any]


class GeminiPlanner:
    """`complete` is trip_core.llm.complete_json unless a test injects a recorded stand-in."""

    def __init__(self, complete: Complete = complete_json) -> None:
        self.complete = complete
        self.rules = FakePlanner()

    def draft(self, brief: TripBrief, signals: list[Signal]) -> Itinerary:
        """The prompt carries the best MAX_SIGNALS signals; the ids it cites are checked against all of them."""
        top = sorted(signals, key=lambda signal: signal.score, reverse=True)[:MAX_SIGNALS]
        result: DraftItinerary = self.complete(
            draft_prompt(brief, top), DraftItinerary, model=model_main(), system=SYSTEM, temperature=0.3
        )
        return to_itinerary(brief, signals, result)

    def questions(self, brief: TripBrief, itinerary: Itinerary) -> list[str]:
        result: Questions = self.complete(
            questions_prompt(brief, itinerary), Questions, model=model_fast(), system=SYSTEM
        )
        asked = [question.strip() for question in result.questions if question.strip()]
        return [question for question in asked if question not in brief.answers][:MAX_QUESTIONS]

    def refine(
        self, brief: TripBrief, itinerary: Itinerary, answers: dict[str, str], signals: list[Signal]
    ) -> list[ItineraryPatch]:
        return self.rules.refine(brief, itinerary, answers, signals)

    def replace_failed(
        self, brief: TripBrief, itinerary: Itinerary, report: VerificationReport, signals: list[Signal]
    ) -> list[ItineraryPatch]:
        """One model call: for each failed stop, a replacement from the unused signal places near its neighbours,
        or a removal. Anything the model returns for a stop that did not fail is ignored."""
        failed = [stop for stop in itinerary.stops() if stop.id in report.failed_stop_ids()]
        if not failed:
            return []
        result: Replacements = self.complete(
            replace_prompt(brief, itinerary, failed, signals), Replacements, model=model_main(), system=SYSTEM
        )
        known = {signal.id for signal in signals}
        by_id = {stop.id: stop for stop in failed}
        patches: list[ItineraryPatch] = []
        seen: set[str] = set()
        for choice in result.replacements:
            old_stop = by_id.get(choice.stop_id)
            if old_stop is None or choice.stop_id in seen:
                continue
            seen.add(choice.stop_id)
            if choice.replacement is None or not choice.replacement.place_name.strip():
                patches.append(ItineraryPatch(op="remove", stop_id=old_stop.id))
                continue
            new_stop = Stop(
                id=f"{old_stop.id}-r",
                day=old_stop.day,
                start=old_stop.start,
                end=old_stop.end,
                place_name=choice.replacement.place_name.strip(),
                category=choice.replacement.category
                if choice.replacement.category in CATEGORIES
                else old_stop.category,
                why=choice.replacement.why.strip() or "Replacement suggested by the planner.",
                signal_ids=[signal_id for signal_id in choice.replacement.signal_ids if signal_id in known],
            )
            patches.append(ItineraryPatch(op="replace", stop_id=old_stop.id, stop=new_stop))
        for stop in failed:
            if stop.id not in seen:
                patches.append(ItineraryPatch(op="remove", stop_id=stop.id))
        return patches


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


def questions_prompt(brief: TripBrief, itinerary: Itinerary) -> str:
    plan = "\n".join(
        f"  day {day_index} {day.date:%a}: " + "; ".join(f"{stop.start:%H:%M} {stop.place_name}" for stop in day.stops)
        for day_index, day in enumerate(itinerary.days)
    )
    answered = "\n".join(f"  {question}" for question in brief.answers) or "  none"
    return (
        f"Trip: {brief.destination}, {brief.travellers} travellers, budget {brief.budget_band.value}, "
        f"styles: {', '.join(brief.styles) or 'any'}.\nDraft:\n{plan}\nAlready answered:\n{answered}\n\n"
        f"Ask at most {MAX_QUESTIONS} short questions whose answers would change this draft: pace, food to avoid, "
        "must-sees, places to skip, budget for meals. One line each, no preamble, nothing already answered."
    )


def replace_prompt(brief: TripBrief, itinerary: Itinerary, failed: list[Stop], signals: list[Signal]) -> str:
    used = {stop.place_name.lower() for stop in itinerary.stops()}
    candidates = [
        f"  {signal.id} | {signal.title} | {', '.join(signal.places_mentioned)}"
        for signal in sorted(signals, key=lambda signal: signal.score, reverse=True)
        if any(place.lower() not in used for place in signal.places_mentioned)
    ][:MAX_SIGNALS]
    days = "\n".join(
        f"  day {index} {day.date:%a %d %b}: "
        + "; ".join(f"[{stop.id}] {stop.start:%H:%M} {stop.place_name}" for stop in day.stops)
        for index, day in enumerate(itinerary.days)
    )
    problems = "\n".join(
        f"  {stop.id}: {stop.place_name} at {stop.start:%H:%M} day {stop.day}: {stop.failure_reason}" for stop in failed
    )
    return (
        f"Trip: {brief.destination}, styles: {', '.join(brief.styles) or 'any'}.\nCurrent plan:\n{days}\n"
        f"These stops failed verification:\n{problems}\n"
        f"Unused signals (id | title | places):\n{chr(10).join(candidates)}\n\n"
        f"For each failed stop choose one replacement: a real, specific place inside {brief.destination} named in "
        "an unused signal, close to the stops before and after it, open at that hour, fitting the trip's styles, "
        "with the signal id. Return replacement = null when nothing fits. Never a place already in the plan, never "
        "another city, never a fragment that is not a place name."
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
