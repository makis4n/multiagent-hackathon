"""The model-backed planner. Gemini through `trip_core.llm`, contract types in and out.

The prompt builders are pure and exported so a test can read the prompt without a model call. Every cap and
every filter lives here in code, after the call: the prompt asks, the code decides.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from trip_core import llm
from trip_core.models import (
    MAX_QUESTIONS,
    Itinerary,
    ItineraryPatch,
    RetryableError,
    Signal,
    ToolError,
    TripBrief,
    VerificationReport,
    apply_patch,
)
from trip_itinerary.schemas import PatchesResponse, QuestionsResponse, to_patches

log = logging.getLogger(__name__)

MAX_PATCHES = 8
SKIP_PREFIX = "skip:"
MODEL_FAILURES = (RetryableError, ToolError, ValidationError)

QUESTIONS_SYSTEM = (
    "You help a travel planner close the gaps in one specific trip plan. "
    "You ask short, concrete questions. You never give advice and you never write the plan."
)

QUESTIONS_PROMPT = """Here is the trip and the plan drafted so far.

{brief}

Plan so far:
{itinerary}

Questions already answered, so do not ask any of these again:
{answered}

Write up to {limit} questions that would most change this plan if they were answered.
Rules for each question:
- one sentence, answerable in a few words
- about a gap this brief leaves open, such as pace, budget, food limits, mobility, or a stop to swap
- about this plan and these stops, not about travel in general
- no question that repeats one already answered above

Return only the questions."""

REFINE_SYSTEM = (
    "You edit an existing trip plan. You answer with patches to that plan and never with a new plan. "
    "You only name stops and signals that were given to you."
)

REFINE_PROMPT = """Here is the trip, the plan the traveller has already seen, and what they just told us.

{brief}

Plan so far:
{itinerary}

What the traveller just answered:
{answers}

Answers collected earlier:
{answered}

Signals you may cite, by id:
{signals}

Write at most {limit} patches that act on these answers and nothing else.
Rules for each patch:
- op is one of add, remove, move, replace
- remove, move and replace name a stop_id from the plan above
- add and replace carry a full stop with a new id, a category, and one sentence of why
- add and move name a target_day inside the plan above, counting from 0
- signal_ids come from the list above; never invent one
- times are HH:MM on a 24 hour clock
- change only what the answers ask for, and leave every other stop alone

Return only the patches."""

REPLACE_SYSTEM = (
    "You repair one trip plan. A few stops failed a check and only those stops may change. "
    "You answer with patches to that plan and never with a new plan."
)

REPLACE_PROMPT = """Here is the trip, the plan the traveller has already seen, and the stops that failed a check.

{brief}

Plan so far:
{itinerary}

Stops that failed, and why:
{failures}

What the traveller told us:
{answered}

Signals you may cite, by id:
{signals}

Places you may not use, because they are already in the plan or the traveller asked to skip them:
{forbidden}

Write exactly one patch for each failed stop above, and touch no other stop.
Rules for each patch:
- op is replace when a different place fits the same slot, otherwise remove
- stop_id is the failed stop
- replace carries a full stop with a new id, a category, one sentence of why, and a place from the signals
- never name a place from the list you may not use, and never the same new place twice
- keep the day and the times of the stop you replace
- signal_ids come from the list above; never invent one
- times are HH:MM on a 24 hour clock

Return only the patches."""


def summarise_brief(brief: TripBrief) -> str:
    """A compact, stable view of the brief for a prompt. Pure."""
    styles = ", ".join(brief.styles) if brief.styles else "none given"
    return "\n".join(
        [
            f"Destination: {brief.destination}",
            f"Origin: {brief.origin}",
            f"Dates: {brief.start_date} to {brief.end_date} ({brief.nights} nights)",
            f"Travellers: {brief.travellers}",
            f"Budget band: {brief.budget_band.value}",
            f"Styles: {styles}",
        ]
    )


def summarise_itinerary(itinerary: Itinerary) -> str:
    """One line per stop, grouped by day. Pure."""
    if not itinerary.days:
        return "no days planned yet"
    lines: list[str] = []
    for index, day in enumerate(itinerary.days):
        lines.append(f"Day {index} ({day.date}):")
        if not day.stops:
            lines.append("  nothing planned")
            continue
        for stop in day.stops:
            slot = f"{stop.start:%H:%M} to {stop.end:%H:%M}"
            lines.append(f"  {stop.id} {slot} {stop.place_name} [{stop.category}] {stop.why}")
    return "\n".join(lines)


def summarise_answers(brief: TripBrief) -> str:
    return summarise_given_answers(brief.answers)


def summarise_given_answers(answers: dict[str, str]) -> str:
    """One line per question and answer. Pure."""
    if not answers:
        return "none yet"
    return "\n".join(f"- {question} -> {answer}" for question, answer in answers.items())


def summarise_signals(signals: list[Signal]) -> str:
    """One line per signal, id first so the model can cite it. Pure."""
    if not signals:
        return "none given"
    lines: list[str] = []
    for signal in signals:
        places = ", ".join(signal.places_mentioned) if signal.places_mentioned else "no place named"
        lines.append(f"- {signal.id} [{signal.source.value}] {signal.title}: {signal.excerpt} (places: {places})")
    return "\n".join(lines)


def skipped_places(brief: TripBrief) -> set[str]:
    """Answers shaped `skip: <place>` name places the traveller does not want. Folded for comparison. Pure."""
    return {
        answer.strip()[len(SKIP_PREFIX) :].strip().casefold()
        for answer in brief.answers.values()
        if answer.strip().casefold().startswith(SKIP_PREFIX)
    }


def summarise_failures(itinerary: Itinerary, report: VerificationReport) -> str:
    """One line per failed stop, with the checks it failed. Pure."""
    failed = report.failed_stop_ids()
    if not failed:
        return "none"
    stops = {stop.id: stop for stop in itinerary.stops()}
    lines: list[str] = []
    for stop_id in failed:
        stop = stops.get(stop_id)
        where = f"{stop.place_name} {stop.start:%H:%M} to {stop.end:%H:%M}" if stop else "no longer in the plan"
        reasons = [
            f"{check.check.value}{f' ({check.detail})' if check.detail else ''}"
            for check in report.checks
            if check.stop_id == stop_id and not check.ok
        ]
        lines.append(f"- {stop_id} {where}: failed {', '.join(reasons)}")
    return "\n".join(lines)


def summarise_forbidden(brief: TripBrief, itinerary: Itinerary) -> str:
    """Every place already in the plan, plus every place an answer skipped. Pure."""
    names = [stop.place_name for stop in itinerary.stops()]
    names += sorted(skipped_places(brief))
    return "\n".join(f"- {name}" for name in names) if names else "none"


def build_questions_prompt(brief: TripBrief, itinerary: Itinerary) -> str:
    """Pure. The exact prompt `questions` sends."""
    return QUESTIONS_PROMPT.format(
        brief=summarise_brief(brief),
        itinerary=summarise_itinerary(itinerary),
        answered=summarise_answers(brief),
        limit=MAX_QUESTIONS,
    )


def build_refine_prompt(brief: TripBrief, itinerary: Itinerary, answers: dict[str, str], signals: list[Signal]) -> str:
    """Pure. The exact prompt `refine` sends."""
    return REFINE_PROMPT.format(
        brief=summarise_brief(brief),
        itinerary=summarise_itinerary(itinerary),
        answers=summarise_given_answers(answers),
        answered=summarise_answers(brief),
        signals=summarise_signals(signals),
        limit=MAX_PATCHES,
    )


def build_replace_failed_prompt(
    brief: TripBrief, itinerary: Itinerary, report: VerificationReport, signals: list[Signal]
) -> str:
    """Pure. The exact prompt `replace_failed` sends."""
    return REPLACE_PROMPT.format(
        brief=summarise_brief(brief),
        itinerary=summarise_itinerary(itinerary),
        failures=summarise_failures(itinerary, report),
        answered=summarise_answers(brief),
        signals=summarise_signals(signals),
        forbidden=summarise_forbidden(brief, itinerary),
    )


def _key(text: str) -> str:
    """Whitespace and case folded away, so a near-repeat of an answered question still counts as the same one."""
    return " ".join(text.split()).casefold()


class GeminiPlanner:
    """Lane C's real `ItineraryPlanner`. `questions`, `refine` and `replace_failed` are model-backed so far."""

    def __init__(self, *, temperature: float = 0.3) -> None:
        self.temperature = temperature
        self.last_dropped: list[str] = []

    def questions(self, brief: TripBrief, itinerary: Itinerary) -> list[str]:
        """At most MAX_QUESTIONS, none of them already answered in the brief. A model failure asks nothing."""
        self.last_dropped = []
        try:
            response = llm.complete_json(
                build_questions_prompt(brief, itinerary),
                QuestionsResponse,
                model=llm.model_fast(),
                system=QUESTIONS_SYSTEM,
                temperature=self.temperature,
            )
        except MODEL_FAILURES as error:
            log.error("questions: the model call failed with %s", type(error).__name__, stack_info=True)
            self.last_dropped.append(f"questions: no questions: the model call raised {type(error).__name__}")
            return []
        return self._select(response.questions, brief)

    @staticmethod
    def _select(candidates: list[str], brief: TripBrief) -> list[str]:
        seen = {_key(question) for question in brief.answers}
        kept: list[str] = []
        for raw in candidates:
            question = raw.strip()
            key = _key(question)
            if not key or key in seen:
                continue
            seen.add(key)
            kept.append(question)
            if len(kept) == MAX_QUESTIONS:
                break
        return kept

    def refine(
        self, brief: TripBrief, itinerary: Itinerary, answers: dict[str, str], signals: list[Signal]
    ) -> list[ItineraryPatch]:
        """Patches only, every one of them applicable, at most MAX_PATCHES. Drops are recorded, never raised.

        A model failure degrades to no patches, so the traveller keeps the itinerary they were already looking at.
        """
        self.last_dropped = []
        try:
            response = llm.complete_json(
                build_refine_prompt(brief, itinerary, answers, signals),
                PatchesResponse,
                model=llm.model_main(),
                system=REFINE_SYSTEM,
                temperature=self.temperature,
            )
        except MODEL_FAILURES as error:
            log.error("refine: the model call failed with %s", type(error).__name__, stack_info=True)
            self.last_dropped.append(f"refine: no patches: the model call raised {type(error).__name__}")
            return []
        mapped = to_patches(response, itinerary, [signal.id for signal in signals])
        self.last_dropped.extend(mapped.dropped)
        return self._applicable(itinerary, mapped.patches)

    def replace_failed(
        self, brief: TripBrief, itinerary: Itinerary, report: VerificationReport, signals: list[Signal]
    ) -> list[ItineraryPatch]:
        """Exactly one patch per failed stop and no other stop touched: a replace in the same slot, or a remove.

        A model failure degrades to no patches, so the run carries on with the itinerary it already had.
        """
        self.last_dropped = []
        failed = report.failed_stop_ids()
        if not failed:
            return []
        try:
            response = llm.complete_json(
                build_replace_failed_prompt(brief, itinerary, report, signals),
                PatchesResponse,
                model=llm.model_main(),
                system=REPLACE_SYSTEM,
                temperature=self.temperature,
            )
        except MODEL_FAILURES as error:
            log.error("replace_failed: the model call failed with %s", type(error).__name__, stack_info=True)
            self.last_dropped.append(f"replace_failed: no patches: the model call raised {type(error).__name__}")
            return []
        mapped = to_patches(response, itinerary, [signal.id for signal in signals])
        self.last_dropped.extend(mapped.dropped)
        return self._applicable(itinerary, self._one_per_failure(brief, itinerary, failed, mapped.patches))

    def _one_per_failure(
        self, brief: TripBrief, itinerary: Itinerary, failed: list[str], candidates: list[ItineraryPatch]
    ) -> list[ItineraryPatch]:
        """The model proposes; this picks one patch per failed stop and nothing else."""
        wanted = set(failed)
        proposed: dict[str, ItineraryPatch] = {}
        for index, patch in enumerate(candidates):
            stop_id = patch.stop_id
            if stop_id is None or stop_id not in wanted:
                self.last_dropped.append(f"failed-stop patch {index}: names no failed stop: {stop_id!r}")
            elif stop_id in proposed:
                self.last_dropped.append(f"failed-stop patch {index}: a second patch for {stop_id}, kept the first")
            else:
                proposed[stop_id] = patch
        taken = {stop.place_name.strip().casefold() for stop in itinerary.stops()} | skipped_places(brief)
        return [self._one_replacement(itinerary, stop_id, proposed.get(stop_id), taken) for stop_id in failed]

    def _one_replacement(
        self, itinerary: Itinerary, stop_id: str, patch: ItineraryPatch | None, taken: set[str]
    ) -> ItineraryPatch:
        removed = ItineraryPatch(op="remove", stop_id=stop_id)
        if patch is None:
            self.last_dropped.append(f"failed stop {stop_id}: the model proposed nothing, removed instead")
            return removed
        if patch.op == "remove":
            return removed
        if patch.op != "replace" or patch.stop is None:
            self.last_dropped.append(f"failed stop {stop_id}: op {patch.op!r} is not a replace, removed instead")
            return removed
        name = patch.stop.place_name.strip()
        if not name or name.casefold() in taken:
            self.last_dropped.append(
                f"failed stop {stop_id}: {name!r} is already in the plan or skipped, removed instead"
            )
            return removed
        taken.add(name.casefold())
        day_index, stop_index = itinerary.locate(stop_id)
        old = itinerary.days[day_index].stops[stop_index]
        keep = patch.stop.model_copy(update={"day": day_index, "start": old.start, "end": old.end})
        return ItineraryPatch(op="replace", stop_id=stop_id, stop=keep)

    def _applicable(self, itinerary: Itinerary, candidates: list[ItineraryPatch]) -> list[ItineraryPatch]:
        """In order, onto an accumulating copy: a later patch may legitimately depend on an earlier one.

        `apply_patch` raises ValueError for its own guards and KeyError out of `Itinerary.locate`, so both.
        """
        kept: list[ItineraryPatch] = []
        state = itinerary
        for index, patch in enumerate(candidates):
            if len(kept) == MAX_PATCHES:
                self.last_dropped.append(f"candidate patch {index}: over the cap of {MAX_PATCHES} patches a round")
                continue
            try:
                state = apply_patch(state, patch)
            except (KeyError, ValueError) as error:
                self.last_dropped.append(f"candidate patch {index}: does not apply: {error}")
                continue
            kept.append(patch)
        return kept
