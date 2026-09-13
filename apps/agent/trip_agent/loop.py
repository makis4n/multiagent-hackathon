"""The loop: brief -> research -> draft -> refine -> resolve -> verify (one replacement pass) -> book -> calendar.

The loop is code. The model only fills typed slots inside the planner. Every tool call goes through CallLog.
Each stage takes the TripState, fills its part and returns it, so the UI can pause between stages (for the
questions, for the booking confirmation) and the CLI can run them back to back through `run`.
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
    ItineraryPatch,
    Replacement,
    Signal,
    StopStatus,
    ToolError,
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
REPLACEMENT_PASSES = 2


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
    state = stage_draft(stage_research(TripState(brief=brief), tools, log), tools, log)
    answers: dict[str, str] = {}
    if ask is not None:
        for question in state.questions:
            answer = ask(question)
            if answer:
                answers[question] = answer
    state = stage_verify(stage_refine(state, tools, log, answers), tools, log)
    state = stage_book(state, tools, log, confirm=confirm, kinds=book)
    return stage_calendar(state, tools, log)


def stage_research(state: TripState, tools: Tools, log: CallLog) -> TripState:
    """Every source runs; one that fails is noted in state.errors and the others still count."""
    signals: list[Signal] = []
    for source in tools.research:
        try:
            signals.extend(log.call(f"research.{source.name}", source.search, state.brief))
        except ToolError as error:
            state.errors.append(f"research.{source.name} failed: {error}")
    if not signals:
        raise ToolError("no research source answered; nothing to draft from")
    state.signals = dedupe(signals)
    return state


def stage_draft(state: TripState, tools: Tools, log: CallLog) -> TripState:
    state.itinerary = log.call("planner.draft", tools.planner.draft, state.brief, state.signals)
    state.questions = log.call("planner.questions", tools.planner.questions, state.brief, state.itinerary)
    return state


def stage_refine(state: TripState, tools: Tools, log: CallLog, answers: dict[str, str]) -> TripState:
    """Merges `answers` into the brief (the brief's own answers win nothing: later answers override) and patches."""
    merged = {**state.brief.answers, **{q: a for q, a in answers.items() if a}}
    state.brief = state.brief.model_copy(update={"answers": merged})
    if state.itinerary is None:
        raise ValueError("refine before draft")
    if merged:
        patches = log.call("planner.refine", tools.planner.refine, state.brief, state.itinerary, merged, state.signals)
        for patch in patches:
            state.itinerary = apply_patch(state.itinerary, patch)
    return state


def stage_verify(state: TripState, tools: Tools, log: CallLog) -> TripState:
    """Resolve and verify; up to REPLACEMENT_PASSES rounds of replacements for what failed; then prune whatever
    still fails so the finished plan is fully verified. Every swap and removal lands in state.replacements."""
    if state.itinerary is None:
        raise ValueError("verify before draft")
    near = state.brief.destination
    itinerary, places = log.call("places.resolve", resolve_places, state.itinerary, tools.resolver, near)
    report = log.call("verifier.verify", tools.verifier.verify, itinerary)
    for _ in range(REPLACEMENT_PASSES):
        if report.passed:
            break
        marked = mark(itinerary, report)
        patches = log.call(
            "planner.replace_failed", tools.planner.replace_failed, state.brief, marked, report, state.signals
        )
        if not patches:
            break
        itinerary = apply_patches(state, marked, itinerary, patches)
        itinerary, places = log.call("places.resolve", resolve_places, itinerary, tools.resolver, near)
        report = log.call("verifier.verify", tools.verifier.verify, itinerary)
    if not report.passed:
        marked = mark(itinerary, report)
        prune = [ItineraryPatch(op="remove", stop_id=stop_id) for stop_id in report.failed_stop_ids()]
        itinerary = apply_patches(state, marked, itinerary, prune)
        itinerary, places = log.call("places.resolve", resolve_places, itinerary, tools.resolver, near)
        report = log.call("verifier.verify", tools.verifier.verify, itinerary)
    state.itinerary = mark(itinerary, report)
    state.places = places
    state.report = report
    return state


def apply_patches(
    state: TripState, marked: Itinerary, itinerary: Itinerary, patches: list[ItineraryPatch]
) -> Itinerary:
    """Applies patches in order and records each swap or removal against the marked (failure-annotated) copy."""
    for patch in patches:
        if patch.stop_id is not None:
            day_index, stop_index = marked.locate(patch.stop_id)
            old = marked.days[day_index].stops[stop_index]
            new = patch.stop if patch.op == "replace" else None
            state.replacements.append(Replacement(old=old, new=new, reason=old.failure_reason or "failed"))
        itinerary = apply_patch(itinerary, patch)
    return itinerary


def stage_search(
    state: TripState, tools: Tools, log: CallLog, kinds: Sequence[BookingKind] = DEFAULT_BOOKINGS
) -> TripState:
    """Searches every kind and records the options. Orders nothing."""
    for kind in kinds:
        options = log.call(f"booking.search.{kind}", tools.booking.search, state.brief, kind)
        state.options.extend(options)
        if not options:
            state.errors.append(f"no {kind} options")
    return state


def stage_book(
    state: TripState,
    tools: Tools,
    log: CallLog,
    *,
    confirm: Confirm,
    kinds: Sequence[BookingKind] = DEFAULT_BOOKINGS,
) -> TripState:
    """Searches when nothing was searched yet; orders only what `confirm` approves, under an idempotency key."""
    if not state.options:
        stage_search(state, tools, log, kinds)
    for kind in kinds:
        chosen = next((option for option in state.options if option.kind == kind), None)
        if chosen is None:
            continue
        confirmed_at = confirm(chosen)
        if confirmed_at is None:
            state.errors.append(f"{kind} not confirmed by the user; nothing ordered")
            continue
        state.orders.append(order(state, tools, log, chosen, confirmed_at))
    return state


def order(state: TripState, tools: Tools, log: CallLog, option: BookingOption, confirmed_at: dt.datetime):
    """One confirmed order. Same brief and offer give the same key, so a repeat never creates a second order."""
    key = idempotency_key(state.brief.id, option)
    return log.call(f"booking.order.{option.kind}", tools.booking.order, option, key, confirmed_at, retries=1)


def stage_calendar(state: TripState, tools: Tools, log: CallLog) -> TripState:
    if state.itinerary is None:
        raise ValueError("calendar before draft")
    state.calendar_url = log.call("calendar.export", tools.calendar.export, state.itinerary, state.brief)
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
