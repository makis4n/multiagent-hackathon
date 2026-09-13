import pytest
from pydantic import BaseModel

from trip_core import llm
from trip_core.llm import SchemaError
from trip_core.models import RetryableError, ToolError


class Ping(BaseModel):
    city: str


def test_retries_a_busy_model_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def flaky(prompt: str, schema: type[Ping], **kwargs: object) -> Ping:
        calls.append(1)
        if len(calls) < 3:
            raise RetryableError("gemini 503: high demand")
        return Ping(city="Kyoto")

    monkeypatch.setattr(llm, "_complete_once", flaky)
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: None)
    assert llm.complete_json("q", Ping).city == "Kyoto"
    assert len(calls) == 3


def test_gives_up_after_the_last_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    def busy(prompt: str, schema: type[Ping], **kwargs: object) -> Ping:
        raise RetryableError("gemini 429: quota")

    monkeypatch.setattr(llm, "_complete_once", busy)
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: None)
    with pytest.raises(RetryableError):
        llm.complete_json("q", Ping, attempts=2)


def test_non_retryable_errors_are_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def broken(prompt: str, schema: type[Ping], **kwargs: object) -> Ping:
        calls.append(1)
        raise ToolError("gemini 404: no such model")

    monkeypatch.setattr(llm, "_complete_once", broken)
    with pytest.raises(ToolError):
        llm.complete_json("q", Ping)
    assert len(calls) == 1


def test_malformed_answer_gets_one_corrective_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    prompts: list[str] = []

    def sloppy(prompt: str, schema: type[Ping], **kwargs: object) -> Ping:
        prompts.append(prompt)
        if len(prompts) == 1:
            raise SchemaError("city: field required")
        return Ping(city="Osaka")

    monkeypatch.setattr(llm, "_complete_once", sloppy)
    assert llm.complete_json("q", Ping).city == "Osaka"
    assert len(prompts) == 2 and "did not match the required schema" in prompts[1]


def test_two_malformed_answers_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    def hopeless(prompt: str, schema: type[Ping], **kwargs: object) -> Ping:
        raise SchemaError("city: field required")

    monkeypatch.setattr(llm, "_complete_once", hopeless)
    with pytest.raises(SchemaError):
        llm.complete_json("q", Ping)
