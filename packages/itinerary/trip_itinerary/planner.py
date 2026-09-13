"""The model-backed planner. Gemini through `trip_core.llm`, contract types in and out.

The prompt builders are pure and exported so a test can read the prompt without a model call. Every cap and
every filter lives here in code, after the call: the prompt asks, the code decides.
"""

from __future__ import annotations

from trip_core import llm
from trip_core.models import MAX_QUESTIONS, Itinerary, TripBrief
from trip_itinerary.schemas import QuestionsResponse

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
    if not brief.answers:
        return "none yet"
    return "\n".join(f"- {question} -> {answer}" for question, answer in brief.answers.items())


def build_questions_prompt(brief: TripBrief, itinerary: Itinerary) -> str:
    """Pure. The exact prompt `questions` sends."""
    return QUESTIONS_PROMPT.format(
        brief=summarise_brief(brief),
        itinerary=summarise_itinerary(itinerary),
        answered=summarise_answers(brief),
        limit=MAX_QUESTIONS,
    )


def _key(text: str) -> str:
    """Whitespace and case folded away, so a near-repeat of an answered question still counts as the same one."""
    return " ".join(text.split()).casefold()


class GeminiPlanner:
    """Lane C's real `ItineraryPlanner`. Only `questions` is model-backed so far."""

    def __init__(self, *, temperature: float = 0.3) -> None:
        self.temperature = temperature

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
