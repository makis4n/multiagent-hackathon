"""The flat shapes the model fills, and the pure mapping from them to contract types.

Gemini's JSON mode rejects dicts and most unions, so the model cannot fill `ItineraryPatch` or `Stop` directly:
times arrive as strings and every op arrives as a plain string. `to_patches` turns that shape into real
`ItineraryPatch` objects. It is pure, it is about shape only, and it never decides whether a patch applies.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal, cast, get_args

from pydantic import BaseModel, Field

from trip_core.models import Itinerary, ItineraryPatch, Stop

OPS: tuple[str, ...] = get_args(ItineraryPatch.model_fields["op"].annotation)


class QuestionsResponse(BaseModel):
    """What `questions` asks the model for. The cap is applied in code, never trusted to the prompt."""

    questions: list[str] = Field(default_factory=list, description="one sentence each, answerable in a few words")


class FlatStop(BaseModel):
    """A `Stop` with the times as HH:MM strings. `place_id` and `status` are not the model's to set."""

    id: str
    day: int = Field(description="0-based index into the itinerary days")
    start: str = Field(description="HH:MM, 24 hour")
    end: str = Field(description="HH:MM, 24 hour")
    place_name: str
    category: str = Field(description="food, sight, museum, walk, nightlife, shopping, nature, rest")
    why: str = Field(description="one sentence that says what the signals said")
    signal_ids: list[str] = Field(default_factory=list, description="ids of the signals given to you, nothing else")


class FlatPatch(BaseModel):
    """An `ItineraryPatch` with `op` as a string and the stop flattened."""

    op: str = Field(description="add, remove, move or replace")
    stop_id: str | None = Field(default=None, description="remove, move, replace: the stop to act on")
    stop: FlatStop | None = Field(default=None, description="add, replace: the new stop")
    target_day: int | None = Field(default=None, description="add, move: the day to put it in")
    position: int | None = Field(default=None, description="add, move: index within the day; None appends")


class PatchesResponse(BaseModel):
    """What `refine` and `replace_failed` ask the model for. One model in, one model out."""

    patches: list[FlatPatch] = Field(default_factory=list)


@dataclass(frozen=True)
class MappingResult:
    """The patches that had a usable shape, and one line per patch that did not.

    Drop lines say `model patch <n>`, numbering into the model's own response, so they never read the same as a
    later drop numbering into this list.
    """

    patches: list[ItineraryPatch] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)


def parse_time(raw: str) -> dt.time:
    """HH:MM into a time. Raises ValueError on anything else."""
    parts = raw.strip().split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f"not HH:MM: {raw!r}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError(f"not a time of day: {raw!r}")
    return dt.time(hour, minute)


def to_patches(response: PatchesResponse, itinerary: Itinerary, signal_ids: Iterable[str]) -> MappingResult:
    """Pure. Flat patches into contract patches, dropping the ones whose shape cannot be trusted."""
    allowed = set(signal_ids)
    known_stop_ids = {stop.id for stop in itinerary.stops()}
    patches: list[ItineraryPatch] = []
    dropped: list[str] = []
    for index, flat in enumerate(response.patches):
        try:
            patches.append(_one(flat, allowed, known_stop_ids))
        except ValueError as error:
            dropped.append(f"model patch {index}: {error}")
    return MappingResult(patches=patches, dropped=dropped)


def _one(flat: FlatPatch, allowed: set[str], known_stop_ids: set[str]) -> ItineraryPatch:
    op = flat.op.strip().lower()
    if op not in OPS:
        raise ValueError(f"unknown op {flat.op!r}")
    stop = _stop(flat.stop, allowed) if flat.stop is not None else None
    if op in {"remove", "move", "replace"} and flat.stop_id not in known_stop_ids:
        raise ValueError(f"{op} names no stop in the itinerary: {flat.stop_id!r}")
    if op in {"add", "replace"} and stop is None:
        raise ValueError(f"{op} needs a stop")
    if op == "add" and stop is not None and stop.id in known_stop_ids:
        raise ValueError(f"add reuses stop id {stop.id!r}")
    return ItineraryPatch(
        op=cast(Literal["add", "remove", "move", "replace"], op),
        stop_id=flat.stop_id,
        stop=stop,
        target_day=flat.target_day,
        position=flat.position,
    )


def _stop(flat: FlatStop, allowed: set[str]) -> Stop:
    return Stop(
        id=flat.id,
        day=flat.day,
        start=parse_time(flat.start),
        end=parse_time(flat.end),
        place_name=flat.place_name,
        category=flat.category,
        why=flat.why,
        signal_ids=[signal_id for signal_id in flat.signal_ids if signal_id in allowed],
    )
