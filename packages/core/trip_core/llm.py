"""The one place that talks to a model. Typed in, typed out.

Claude is the default (LLM_PROVIDER=anthropic): the response schema goes in as a forced tool call, so the answer
is JSON in the shape asked for. Gemini stays behind LLM_PROVIDER=gemini as the fallback it was before, with the
same wrapper contract. Override models with ANTHROPIC_MODEL_MAIN / ANTHROPIC_MODEL_FAST (or GEMINI_MODEL_*).

Keep response schemas flat: pydantic models built from str, int, float, bool, lists and nested models, with
`X | None` as the only union. No dicts. Both providers accept that subset; Gemini rejects the rest.
"""

from __future__ import annotations

import os
import time
from typing import Any

import anthropic
from anthropic.types import MessageParam, ToolChoiceToolParam, ToolParam
from pydantic import BaseModel, ValidationError

from trip_core.models import RetryableError, ToolError

DEFAULT_PROVIDER = "anthropic"
DEFAULTS = {
    "anthropic": ("claude-sonnet-5", "claude-haiku-4-5-20251001"),
    "gemini": ("gemini-flash-lite-latest", "gemini-flash-lite-latest"),
}
RETRYABLE_CODES = {408, 409, 429, 500, 502, 503, 504, 529}
BACKOFF_SECONDS = 3.0
MAX_TOKENS = 8192
ANSWER_TOOL = "answer"

_anthropic: anthropic.Anthropic | None = None
_gemini: Any = None


def provider() -> str:
    name = os.environ.get("LLM_PROVIDER", DEFAULT_PROVIDER).strip().lower()
    if name not in DEFAULTS:
        raise ToolError(f"LLM_PROVIDER must be one of {sorted(DEFAULTS)}, not {name!r}")
    return name


def model_main() -> str:
    name = provider()
    return os.environ.get(f"{name.upper()}_MODEL_MAIN", DEFAULTS[name][0])


def model_fast() -> str:
    name = provider()
    return os.environ.get(f"{name.upper()}_MODEL_FAST", DEFAULTS[name][1])


def complete_json[T: BaseModel](
    prompt: str,
    schema: type[T],
    *,
    model: str | None = None,
    system: str | None = None,
    temperature: float = 0.2,
    attempts: int = 4,
) -> T:
    """One structured call: short backoff on 429 and 5xx, one corrective retry when the answer does not
    match the schema. RetryableError once `attempts` are spent, ToolError on anything a retry will not fix."""
    corrected = False
    for attempt in range(1, attempts + 1):
        try:
            return _complete_once(prompt, schema, model=model, system=system, temperature=temperature)
        except SchemaError as error:
            if corrected:
                raise
            corrected = True
            prompt = (
                f"{prompt}\n\nYour previous answer did not match the required schema: {error}\n"
                "Return only JSON that matches it."
            )
        except RetryableError:
            if attempt == attempts:
                raise
            time.sleep(BACKOFF_SECONDS * attempt)
    raise AssertionError("unreachable")


class SchemaError(ToolError):
    """The model answered, but not in the shape asked for. One corrective retry, then it propagates."""


def _complete_once[T: BaseModel](
    prompt: str, schema: type[T], *, model: str | None, system: str | None, temperature: float
) -> T:
    if provider() == "gemini":
        return _gemini_once(prompt, schema, model=model or model_main(), system=system, temperature=temperature)
    return _anthropic_once(prompt, schema, model=model or model_main(), system=system)


def anthropic_client() -> anthropic.Anthropic:
    global _anthropic
    if _anthropic is None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ToolError("ANTHROPIC_API_KEY is not set; copy .env.example to .env and fill it in")
        _anthropic = anthropic.Anthropic(api_key=key, max_retries=0, timeout=120.0)
    return _anthropic


def _anthropic_once[T: BaseModel](prompt: str, schema: type[T], *, model: str, system: str | None) -> T:
    """The schema is the only tool and the call is forced to use it, so the answer is its input. Claude 5 takes
    no temperature; the wrapper keeps the parameter for Gemini."""
    tool = ToolParam(
        name=ANSWER_TOOL,
        description=f"Record the answer as {schema.__name__}.",
        input_schema=schema.model_json_schema(),
    )
    messages: list[MessageParam] = [{"role": "user", "content": prompt}]
    try:
        response = anthropic_client().messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system if system else anthropic.omit,
            messages=messages,
            tools=[tool],
            tool_choice=ToolChoiceToolParam(type="tool", name=ANSWER_TOOL),
        )
    except anthropic.APIStatusError as error:
        if error.status_code in RETRYABLE_CODES:
            raise RetryableError(f"anthropic {error.status_code}: {error.message}") from error
        raise ToolError(f"anthropic {error.status_code}: {error.message}") from error
    except anthropic.APIConnectionError as error:
        raise RetryableError(f"anthropic: {type(error).__name__}") from error
    payload = next((block.input for block in response.content if block.type == "tool_use"), None)
    if payload is None:
        raise SchemaError(f"no tool answer (stop_reason={response.stop_reason})")
    try:
        return schema.model_validate(payload)
    except ValidationError as error:
        raise SchemaError(str(error)[:800]) from error


def gemini_client() -> Any:
    global _gemini
    if _gemini is None:
        from google import genai

        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ToolError("GEMINI_API_KEY is not set; copy .env.example to .env and fill it in")
        _gemini = genai.Client(api_key=key)
    return _gemini


def _gemini_once[T: BaseModel](
    prompt: str, schema: type[T], *, model: str, system: str | None, temperature: float
) -> T:
    from google.genai import errors, types

    try:
        response = gemini_client().models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_schema=schema,
                temperature=temperature,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
    except errors.APIError as error:
        if error.code in RETRYABLE_CODES:
            raise RetryableError(f"gemini {error.code}: {error.message}") from error
        raise ToolError(f"gemini {error.code}: {error.message}") from error
    text = response.text
    if not text:
        raise SchemaError("empty response")
    try:
        return schema.model_validate_json(text)
    except ValidationError as error:
        raise SchemaError(str(error)[:800]) from error
