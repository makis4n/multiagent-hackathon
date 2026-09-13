"""The loop: brief -> research -> draft -> refine -> resolve -> verify (one replacement pass) -> book -> calendar.

The loop is code. The model only fills typed slots inside the planner. Every tool call goes through CallLog.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from trip_agent.log import CallLog
from trip_core.models import (
    BookingKind,
    BookingOption,
    Itinerary,
    Signal,
    StopStatus,
    TripBrief,
    TripState,
    VerificationReport,
    apply_patch,
    idempotency_key,
)
from trip_core.tools import (
    BookingProvider,
    CalendarSink,
    ItineraryPlanner,
    PlaceResolver,
    ResearchSource,
    Verifier,
    resolve_places,
)

Confirm = Callable[[BookingOption], dt.datetime | None]
Ask = Callable[[str], str | None]
DEFAULT_BOOKINGS: tuple[BookingKind, ...] = (BookingKind.flight, BookingKind.stay)


@dataclass
class Tools:
    research: list[ResearchSource]
    resolver: PlaceResolver
    planner: ItineraryPlanner
    verifier: Verifier
    booking: BookingProvider
    calendar: CalendarSink


def run(
    brief: TripBrief,
    tools: Tools,
    log: CallLog,
    *,
    confirm: Confirm,
    ask: Ask | None = None,
    book: Sequence[BookingKind] = DEFAULT_BOOKINGS,
) -> TripState:
    """One trip, start to finish. `confirm` returns the moment the user approved an option, or None to skip it."""
    state = TripState(brief=brief)

    for source in tools.research:
        state.signals.extend(log.call(f"research.{source.name}", source.search, brief))
    state.signals = dedupe(state.signals)

    itinerary = log.call("planner.draft", tools.planner.draft, brief, state.signals)

    state.questions = log.call("planner.questions", tools.planner.questions, brief, itinerary)
    answers = dict(brief.answers)
    for question in state.questions:
        if question in answers or ask is None:
            continue
        answer = ask(question)
        if answer:
            answers[question] = answer
    brief = brief.model_copy(update={"answers": answers})
    state.brief = brief
    if answers:
        patches = log.call("planner.refine", tools.planner.refine, brief, itinerary, answers, state.signals)
        for patch in patches:
            itinerary = apply_patch(itinerary, patch)

    itinerary, places = log.call("places.resolve", resolve_places, itinerary, tools.resolver, brief.destination)
    report = log.call("verifier.verify", tools.verifier.verify, itinerary)
    if not report.passed:
        patches = log.call(
            "planner.replace_failed",
            tools.planner.replace_failed,
            brief,
            mark(itinerary, report),
            report,
            state.signals,
        )
        for patch in patches:
            itinerary = apply_patch(itinerary, patch)
        itinerary, places = log.call("places.resolve", resolve_places, itinerary, tools.resolver, brief.destination)
        report = log.call("verifier.verify", tools.verifier.verify, itinerary)
    itinerary = mark(itinerary, report)
    state.itinerary = itinerary
    state.places = places
    state.report = report

    for kind in book:
        options = log.call(f"booking.search.{kind}", tools.booking.search, brief, kind)
        state.options.extend(options)
        if not options:
            state.errors.append(f"no {kind} options")
            continue
        chosen = options[0]
        confirmed_at = confirm(chosen)
        if confirmed_at is None:
            state.errors.append(f"{kind} not confirmed by the user; nothing ordered")
            continue
        key = idempotency_key(brief.id, chosen)
        order = log.call(f"booking.order.{kind}", tools.booking.order, chosen, key, confirmed_at, retries=1)
        state.orders.append(order)

    state.calendar_url = log.call("calendar.export", tools.calendar.export, itinerary, brief)
    return state


def dedupe(signals: list[Signal]) -> list[Signal]:
    """One signal per URL, the best-scored one, best first."""
    by_url: dict[str, Signal] = {}
    for signal in signals:
        current = by_url.get(signal.url)
        if current is None or signal.score > current.score:
            by_url[signal.url] = signal
    return sorted(by_url.values(), key=lambda signal: signal.score, reverse=True)


def mark(itinerary: Itinerary, report: VerificationReport) -> Itinerary:
    """Pure. Stamps every stop verified or failed, with the first failing detail as the reason."""
    result = itinerary.model_copy(deep=True)
    reasons: dict[str, str] = {}
    for check in report.checks:
        if not check.ok and check.stop_id not in reasons:
            reasons[check.stop_id] = f"{check.check}: {check.detail}"
    for stop in result.stops():
        stop.status = StopStatus.failed if stop.id in reasons else StopStatus.verified
        stop.failure_reason = reasons.get(stop.id)
    return result
