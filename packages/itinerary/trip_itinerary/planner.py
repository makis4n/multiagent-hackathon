"""The model-backed planner. Gemini through `trip_core.llm`, contract types in and out.

The prompt builders are pure and exported so a test can read the prompt without a model call. Every cap and
every filter lives here in code, after the call: the prompt asks, the code decides.
"""

from __future__ import annotations

from trip_core import llm
from trip_core.models import MAX_QUESTIONS, Itinerary, ItineraryPatch, Signal, TripBrief, apply_patch
from trip_itinerary.schemas import PatchesResponse, QuestionsResponse, to_patches

MAX_PATCHES = 8

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


def _key(text: str) -> str:
    """Whitespace and case folded away, so a near-repeat of an answered question still counts as the same one."""
    return " ".join(text.split()).casefold()


class GeminiPlanner:
    """Lane C's real `ItineraryPlanner`. `questions` and `refine` are model-backed so far."""

    def __init__(self, *, temperature: float = 0.3) -> None:
        self.temperature = temperature
        self.last_dropped: list[str] = []

    def questions(self, brief: TripBrief, itinerary: Itinerary) -> list[str]:
        """At most MAX_QUESTIONS, none of them already answered in the brief."""
        response = llm.complete_json(
            build_questions_prompt(brief, itinerary),
            QuestionsResponse,
            model=llm.model_fast(),
            system=QUESTIONS_SYSTEM,
            temperature=self.temperature,
        )
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
        """Patches only, every one of them applicable, at most MAX_PATCHES. Drops are recorded, never raised."""
        self.last_dropped = []
        response = llm.complete_json(
            build_refine_prompt(brief, itinerary, answers, signals),
            PatchesResponse,
            model=llm.model_main(),
            system=REFINE_SYSTEM,
            temperature=self.temperature,
        )
        mapped = to_patches(response, itinerary, [signal.id for signal in signals])
        self.last_dropped.extend(mapped.dropped)
        return self._applicable(itinerary, mapped.patches)

    def _applicable(self, itinerary: Itinerary, candidates: list[ItineraryPatch]) -> list[ItineraryPatch]:
        """In order, onto an accumulating copy: a later patch may legitimately depend on an earlier one.

        `apply_patch` raises ValueError for its own guards and KeyError out of `Itinerary.locate`, so both.
        """
        kept: list[ItineraryPatch] = []
        state = itinerary
        for index, patch in enumerate(candidates):
            if len(kept) == MAX_PATCHES:
                self.last_dropped.append(f"patch {index}: over the cap of {MAX_PATCHES} patches a round")
                continue
            try:
                state = apply_patch(state, patch)
            except (KeyError, ValueError) as error:
                self.last_dropped.append(f"patch {index}: does not apply: {error}")
                continue
            kept.append(patch)
        return kept
