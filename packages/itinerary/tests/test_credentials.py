import datetime as dt
import importlib
import json
import stat
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from google.oauth2.credentials import Credentials

from trip_core.models import ToolError
from trip_itinerary.credentials import CREDENTIALS_ENV, TOKEN_PATH_ENV, GoogleTokenProvider, default_token_path

CLIENT_CONFIG = json.dumps(
    {"installed": {"client_id": "fake-client", "client_secret": "fake-secret", "token_uri": "https://example.invalid"}}
)


def naive_utc_now() -> dt.datetime:
    """google-auth stores expiry as a naive UTC datetime."""
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def authorized_user(token: str, expiry: dt.datetime) -> str:
    return json.dumps(
        {
            "token": token,
            "refresh_token": "fake-refresh",
            "client_id": "fake-client",
            "client_secret": "fake-secret",
            "scopes": ["https://www.googleapis.com/auth/calendar"],
            "expiry": expiry.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    )


def exploding_flow(config: Mapping[str, Any], scopes: tuple[str, ...]) -> Credentials:
    raise AssertionError("the OAuth flow ran when a valid cached token was available")


class RecordingFlow:
    def __init__(self, token: str) -> None:
        self.calls = 0
        self._token = token

    def __call__(self, config: Mapping[str, Any], scopes: tuple[str, ...]) -> Credentials:
        self.calls += 1
        return Credentials(
            token=self._token,
            refresh_token="fake-refresh",
            token_uri="https://example.invalid",
            client_id="fake-client",
            client_secret="fake-secret",
            scopes=list(scopes),
            expiry=naive_utc_now() + dt.timedelta(hours=1),
        )


def test_missing_credentials_names_the_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CREDENTIALS_ENV, raising=False)
    monkeypatch.setenv(TOKEN_PATH_ENV, str(tmp_path / "token.json"))
    provider = GoogleTokenProvider(flow_runner=exploding_flow)
    with pytest.raises(ToolError) as caught:
        provider.token()
    assert ".env" in str(caught.value)


def test_import_does_not_read_the_environment() -> None:
    source = "import os; os.environ.pop('GOOGLE_CALENDAR_CREDENTIALS_JSON', None); import trip_itinerary.credentials"
    done = subprocess.run([sys.executable, "-c", source], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr


def test_a_valid_cached_token_is_reused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = tmp_path / "token.json"
    cache.write_text(authorized_user("cached-token", naive_utc_now() + dt.timedelta(hours=2)))
    monkeypatch.setenv(CREDENTIALS_ENV, CLIENT_CONFIG)
    monkeypatch.setenv(TOKEN_PATH_ENV, str(cache))
    provider = GoogleTokenProvider(flow_runner=exploding_flow)
    assert provider.token() == "cached-token"


def test_an_expired_cached_token_runs_the_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = tmp_path / "token.json"
    cache.write_text(authorized_user("stale-token", naive_utc_now() - dt.timedelta(hours=2)))
    monkeypatch.setenv(CREDENTIALS_ENV, CLIENT_CONFIG)
    monkeypatch.setenv(TOKEN_PATH_ENV, str(cache))
    flow = RecordingFlow("fresh-token")
    provider = GoogleTokenProvider(flow_runner=flow)
    monkeypatch.setattr(provider, "_refresh", lambda creds: None)
    assert provider.token() == "fresh-token"
    assert flow.calls == 1


def test_a_missing_cached_token_runs_the_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CREDENTIALS_ENV, CLIENT_CONFIG)
    monkeypatch.setenv(TOKEN_PATH_ENV, str(tmp_path / "absent" / "token.json"))
    flow = RecordingFlow("fresh-token")
    provider = GoogleTokenProvider(flow_runner=flow)
    assert provider.token() == "fresh-token"
    assert flow.calls == 1


def test_the_cache_file_is_owner_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = tmp_path / "nested" / "token.json"
    monkeypatch.setenv(CREDENTIALS_ENV, CLIENT_CONFIG)
    monkeypatch.setenv(TOKEN_PATH_ENV, str(cache))
    GoogleTokenProvider(flow_runner=RecordingFlow("fresh-token")).token()
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600


def test_the_default_cache_path_is_outside_the_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TOKEN_PATH_ENV, raising=False)
    repo = Path(importlib.import_module("trip_itinerary").__file__ or ".").resolve().parents[3]
    assert not default_token_path().resolve().is_relative_to(repo)


def test_a_repository_local_token_override_is_rejected_before_storing(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Path(importlib.import_module("trip_itinerary").__file__ or ".").resolve().parents[3]
    target = repo / "calendar-token-must-not-be-written.json"
    monkeypatch.chdir(repo)
    monkeypatch.setenv(CREDENTIALS_ENV, CLIENT_CONFIG)
    monkeypatch.setenv(TOKEN_PATH_ENV, target.name)
    flow = RecordingFlow("fresh-token")

    with pytest.raises(ToolError, match="must point outside the repository"):
        GoogleTokenProvider(flow_runner=flow).token()

    assert flow.calls == 0
    assert not target.exists()


def test_credentials_path_is_rejected_as_json_without_reading_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    credentials_file = tmp_path / "credentials.json"
    credentials_file.write_text(CLIENT_CONFIG)
    monkeypatch.setenv(CREDENTIALS_ENV, str(credentials_file))
    monkeypatch.setenv(TOKEN_PATH_ENV, str(tmp_path / "token.json"))

    def read_forbidden(self: Path, *, encoding: str | None = None) -> str:
        raise AssertionError(f"credentials must not be read from {self}")

    monkeypatch.setattr(Path, "read_text", read_forbidden)
    with pytest.raises(ToolError, match="must be JSON supplied in .env"):
        GoogleTokenProvider(flow_runner=exploding_flow).token()
