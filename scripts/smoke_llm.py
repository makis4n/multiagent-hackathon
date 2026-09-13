"""One real Gemini call through trip_core.llm. Usage: make smoke-llm (needs GEMINI_API_KEY in .env)."""

from __future__ import annotations

import sys
import time

from dotenv import load_dotenv
from pydantic import BaseModel

from trip_core.llm import complete_json, model_fast, model_main


class Ping(BaseModel):
    city: str
    three_things: list[str]
    one_sentence_why: str


def main() -> int:
    load_dotenv()
    for model in (model_fast(), model_main()):
        started = time.perf_counter()
        result = complete_json(
            "Name one city in Japan worth five days in November and three things to do there.",
            Ping,
            model=model,
            system="Answer for a traveller who likes food and art. Be concrete.",
        )
        print(f"{model}: {time.perf_counter() - started:.1f}s -> {result.model_dump_json()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
