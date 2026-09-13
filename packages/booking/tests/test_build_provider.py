"""Offline. build_provider() validates the key before any client or network call exists."""

from __future__ import annotations

import pytest

from trip_booking import build_provider
from trip_core.models import ToolError


def test_a_missing_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUFFEL_API_KEY", raising=False)
    with pytest.raises(ToolError):
        build_provider()


def test_a_live_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUFFEL_API_KEY", "duffel_live_abc123")
    with pytest.raises(ToolError):
        build_provider()


def test_a_sandbox_key_builds_a_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUFFEL_API_KEY", "duffel_test_abc123")
    provider = build_provider()
    assert provider.name == "duffel"
