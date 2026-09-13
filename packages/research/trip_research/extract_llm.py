"""Optional, model-backed refinement of Signal.places_mentioned. Never used for Reddit content: Reddit's
Responsible Builder Policy restricts sharing post data with third-party AI. YouTube and Exa content carries no
such restriction, and a model reads through webpage boilerplate and clickbait framing that the heuristic in
places.py cannot (see packages/research/tests/cassettes/README.md for what that heuristic still misses).

Best-effort by design: this sits on top of the heuristic's output, not instead of it. Any failure at all, a
missing key, a rate limit, a malformed answer, leaves every signal's heuristic places_mentioned untouched. A
source's search() must never raise because of this (apps/agent/trip_agent/loop.py runs research with retries=0),
so refine_places() never raises either.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from trip_core.llm import complete_json, model_fast
from trip_core.models import RetryableError, Signal, ToolError

MAX_PLACES = 4
MAX_REFINE = 40
MAX_TITLE_CHARS = 200
MAX_EXCERPT_CHARS = 400

SYSTEM = (
    "You extract real, specific named places from travel content: a venue, a restaurant, a neighbourhood, a "
    "landmark. Never a generic word (food, guide, market), never a website, channel or sponsor's own name, "
    "never the destination city or country by itself. If a numbered item names nothing specific, return an "
    "empty list for it."
)


class _SignalPlaces(BaseModel):
    index: int
    places: list[str] = Field(default_factory=list)


class _Batch(BaseModel):
    items: list[_SignalPlaces]


def build_prompt(signals: list[Signal], destination: str) -> str:
    """Pure, so the prompt shape is testable without a key or a network call."""
    lines = [f"Destination: {destination}", ""]
    for index, signal in enumerate(signals):
        lines.append(f"{index}. title: {signal.title[:MAX_TITLE_CHARS]!r}")
        lines.append(f"   excerpt: {signal.excerpt[:MAX_EXCERPT_CHARS]!r}")
    return "\n".join(lines)


def refine_places(signals: list[Signal], destination: str) -> list[Signal]:
    """Refines the first MAX_REFINE signals in place-order; the rest keep their heuristic result untouched.
    Falls back to every signal's existing places_mentioned on any failure, so this is always safe to call.

    An empty list from the model is a real answer ("nothing specific here"), not a miss: it replaces the
    heuristic's guess. Only an index the model dropped entirely from its response falls back to the heuristic,
    since that is the one case where we have no judgment from the model to trust."""
    if not signals:
        return signals
    batch = signals[:MAX_REFINE]
    try:
        result = complete_json(build_prompt(batch, destination), _Batch, model=model_fast(), system=SYSTEM)
    except (RetryableError, ToolError):
        return signals
    by_index = {item.index: item.places[:MAX_PLACES] for item in result.items}
    refined = [
        signal.model_copy(update={"places_mentioned": by_index[index]}) if index in by_index else signal
        for index, signal in enumerate(batch)
    ]
    return refined + signals[MAX_REFINE:]
