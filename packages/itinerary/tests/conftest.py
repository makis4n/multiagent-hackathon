"""Every test in this package runs offline. A test that forgets its stub fails here instead of calling Gemini."""

from __future__ import annotations

from typing import Any, Never

import pytest
from pydantic import BaseModel

from trip_core import llm


@pytest.fixture(autouse=True)
def no_live_model(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(prompt: str, schema: type[BaseModel], **kwargs: Any) -> Never:
        raise AssertionError(f"{request.node.nodeid} called trip_core.llm.complete_json without a stub")

    monkeypatch.setattr(llm, "complete_json", refuse)
