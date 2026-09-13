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


class _Block:
    def __init__(self, type: str, input: object = None) -> None:
        self.type = type
        self.input = input


class _Response:
    def __init__(self, blocks: list[_Block], stop_reason: str = "tool_use") -> None:
        self.content = blocks
        self.stop_reason = stop_reason


class _Messages:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.requests: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.requests.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class _Client:
    def __init__(self, outcome: object) -> None:
        self.messages = _Messages(outcome)


def _use(monkeypatch: pytest.MonkeyPatch, outcome: object) -> _Client:
    client = _Client(outcome)
    monkeypatch.setattr(llm, "anthropic_client", lambda: client)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    return client


def test_claude_answers_through_the_forced_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _use(monkeypatch, _Response([_Block("text"), _Block("tool_use", {"city": "Nara"})]))
    assert llm.complete_json("q", Ping, system="s").city == "Nara"
    sent = client.messages.requests[0]
    assert sent["tool_choice"] == {"type": "tool", "name": llm.ANSWER_TOOL}
    assert sent["system"] == "s"


def test_claude_wrong_shape_is_a_schema_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _Response([_Block("tool_use", {"town": "Nara"})]))
    with pytest.raises(SchemaError):
        llm.complete_json("q", Ping)


def test_claude_overloaded_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    import anthropic
    import httpx2 as httpx

    response = httpx.Response(529, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    _use(monkeypatch, anthropic.APIStatusError("overloaded", response=response, body=None))
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: None)
    with pytest.raises(RetryableError):
        llm.complete_json("q", Ping, attempts=2)


def test_claude_bad_request_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    import anthropic
    import httpx2 as httpx

    response = httpx.Response(400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    client = _use(monkeypatch, anthropic.APIStatusError("bad request", response=response, body=None))
    with pytest.raises(ToolError):
        llm.complete_json("q", Ping)
    assert len(client.messages.requests) == 1
