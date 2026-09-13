"""The one place that talks to Gemini. Typed in, typed out.

Defaults are the `-latest` aliases: the dated 2.5 names are refused for new keys and the Pro models need paid
quota. Override with GEMINI_MODEL_MAIN and GEMINI_MODEL_FAST in .env.

Keep response schemas flat: pydantic models built from str, int, float, bool, lists and nested models, with
`X | None` as the only union. No dicts. Gemini's JSON schema support rejects the rest.
"""

from __future__ import annotations

import os
import time

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from trip_core.models import RetryableError, ToolError

DEFAULT_MAIN = "gemini-flash-latest"
DEFAULT_FAST = "gemini-flash-lite-latest"
RETRYABLE_CODES = {408, 429, 500, 502, 503, 504}
BACKOFF_SECONDS = 2.0

_client: genai.Client | None = None


def model_main() -> str:
    return os.environ.get("GEMINI_MODEL_MAIN", DEFAULT_MAIN)


def model_fast() -> str:
    return os.environ.get("GEMINI_MODEL_FAST", DEFAULT_FAST)


def client() -> genai.Client:
    global _client
    if _client is None:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ToolError("GEMINI_API_KEY is not set; copy .env.example to .env and fill it in")
        _client = genai.Client(api_key=key)
    return _client


def complete_json[T: BaseModel](
    prompt: str,
    schema: type[T],
    *,
    model: str | None = None,
    system: str | None = None,
    temperature: float = 0.2,
    attempts: int = 3,
) -> T:
    """One structured call with short backoff on 429 and 5xx. RetryableError once `attempts` are spent,
    ToolError on anything a retry will not fix."""
    for attempt in range(1, attempts + 1):
        try:
            return _complete_once(prompt, schema, model=model, system=system, temperature=temperature)
        except RetryableError:
            if attempt == attempts:
                raise
            time.sleep(BACKOFF_SECONDS * attempt)
    raise AssertionError("unreachable")


def _complete_once[T: BaseModel](
    prompt: str, schema: type[T], *, model: str | None, system: str | None, temperature: float
) -> T:
    try:
        response = client().models.generate_content(
            model=model or model_main(),
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
        raise ToolError("gemini returned no text")
    return schema.model_validate_json(text)
