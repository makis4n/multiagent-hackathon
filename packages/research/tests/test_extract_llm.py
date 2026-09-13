"""Offline. complete_json is monkeypatched, same convention as packages/core/tests/test_llm.py: no key, no
network, no respx needed since this never goes through httpx directly."""

from __future__ import annotations

import pytest

from trip_core.models import RetryableError, Signal, SignalSource, ToolError
from trip_research import extract_llm
from trip_research.extract_llm import MAX_PLACES, MAX_REFINE, _Batch, _SignalPlaces, build_prompt, refine_places


def signal(signal_id: str, title: str, places: list[str] | None = None) -> Signal:
    return Signal(
        id=signal_id,
        source=SignalSource.web,
        url=f"https://example.com/{signal_id}",
        title=title,
        excerpt="",
        places_mentioned=places or [],
    )


def test_build_prompt_indexes_every_signal() -> None:
    prompt = build_prompt([signal("a", "Tsukiji Outer Market at 7am"), signal("b", "teamLab Planets")], "Tokyo")
    assert "Destination: Tokyo" in prompt
    assert "0. title: 'Tsukiji Outer Market at 7am'" in prompt
    assert "1. title: 'teamLab Planets'" in prompt


def test_refine_places_replaces_the_heuristic_result_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(prompt: str, schema: type[_Batch], **kwargs: object) -> _Batch:
        return _Batch(items=[_SignalPlaces(index=0, places=["Ain Soph"])])

    monkeypatch.setattr(extract_llm, "complete_json", fake)
    refined = refine_places([signal("a", "junk title", places=["About", "Blog"])], "Tokyo")
    assert refined[0].places_mentioned == ["Ain Soph"]


def test_an_explicit_empty_answer_clears_the_heuristic_guess(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bug this guards: an empty list from the model is a real judgment ("nothing specific here"), not a
    miss. Treating it as a miss meant every signal the model correctly emptied kept its old heuristic noise."""

    def fake(prompt: str, schema: type[_Batch], **kwargs: object) -> _Batch:
        return _Batch(items=[_SignalPlaces(index=0, places=[])])

    monkeypatch.setattr(extract_llm, "complete_json", fake)
    refined = refine_places([signal("a", "junk", places=["Squarespace"])], "Tokyo")
    assert refined[0].places_mentioned == []


def test_an_index_missing_from_the_response_keeps_its_heuristic_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """Different from an explicit empty list: the model dropped this index from its answer entirely, so
    there is no judgment to trust and the heuristic's guess is all there is."""

    def fake(prompt: str, schema: type[_Batch], **kwargs: object) -> _Batch:
        return _Batch(items=[])

    monkeypatch.setattr(extract_llm, "complete_json", fake)
    refined = refine_places([signal("a", "junk", places=["Asakusa"])], "Tokyo")
    assert refined[0].places_mentioned == ["Asakusa"]


def test_falls_back_on_a_retryable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def busy(prompt: str, schema: type[_Batch], **kwargs: object) -> _Batch:
        raise RetryableError("gemini 429: quota")

    monkeypatch.setattr(extract_llm, "complete_json", busy)
    original = [signal("a", "junk", places=["Asakusa"])]
    assert refine_places(original, "Tokyo") == original


def test_falls_back_on_a_tool_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(prompt: str, schema: type[_Batch], **kwargs: object) -> _Batch:
        raise ToolError("gemini 404: no such model")

    monkeypatch.setattr(extract_llm, "complete_json", broken)
    original = [signal("a", "junk", places=["Asakusa"])]
    assert refine_places(original, "Tokyo") == original


def test_a_returned_list_is_capped_at_max_places(monkeypatch: pytest.MonkeyPatch) -> None:
    def generous(prompt: str, schema: type[_Batch], **kwargs: object) -> _Batch:
        return _Batch(items=[_SignalPlaces(index=0, places=[f"Place {n}" for n in range(10)])])

    monkeypatch.setattr(extract_llm, "complete_json", generous)
    refined = refine_places([signal("a", "junk")], "Tokyo")
    assert len(refined[0].places_mentioned) == MAX_PLACES


def test_only_the_first_max_refine_signals_reach_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []

    def fake(prompt: str, schema: type[_Batch], **kwargs: object) -> _Batch:
        seen.append(prompt.count("title:"))
        return _Batch(items=[])

    monkeypatch.setattr(extract_llm, "complete_json", fake)
    signals = [signal(f"s{n}", "junk", places=["kept"]) for n in range(MAX_REFINE + 5)]
    refined = refine_places(signals, "Tokyo")

    assert seen == [MAX_REFINE]
    assert all(s.places_mentioned == ["kept"] for s in refined[MAX_REFINE:])


def test_empty_list_is_a_noop() -> None:
    assert refine_places([], "Tokyo") == []
