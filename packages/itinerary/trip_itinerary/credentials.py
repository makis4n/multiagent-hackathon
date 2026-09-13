"""Credentials for the Google Calendar API. Nothing here knows what a calendar is.

The calendar client takes a `TokenProvider` so a test can inject a stub and the interactive OAuth flow never
runs offline. `GOOGLE_CALENDAR_CREDENTIALS_JSON` is read at the first call, never at import. The token is
cached outside the repository, owner-readable only, and reused while it is still valid.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from google.auth.exceptions import GoogleAuthError, TransportError
from google.oauth2.credentials import Credentials

from trip_core.models import RetryableError, ToolError

log = logging.getLogger(__name__)

CALENDAR_SCOPES: tuple[str, ...] = ("https://www.googleapis.com/auth/calendar",)
CREDENTIALS_ENV = "GOOGLE_CALENDAR_CREDENTIALS_JSON"
TOKEN_PATH_ENV = "TRIP_CALENDAR_TOKEN_PATH"
_CACHE_DIR = "trip-agent"
_CACHE_FILE = "google-calendar-token.json"

FlowRunner = Callable[[Mapping[str, Any], tuple[str, ...]], Credentials]


@runtime_checkable
class TokenProvider(Protocol):
    """A bearer token for the Calendar API. The client depends on this, not on the OAuth flow."""

    def token(self) -> str: ...


class StaticTokenProvider:
    """A token that is already in hand. The seam tests and the fakes use."""

    def __init__(self, value: str) -> None:
        self._value = value

    def token(self) -> str:
        return self._value


def default_token_path() -> Path:
    """Outside the repository by design, so no token can land in the working tree."""
    override = os.environ.get(TOKEN_PATH_ENV)
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".cache"
    return root / _CACHE_DIR / _CACHE_FILE


class GoogleTokenProvider:
    """Reads the client config from the environment, caches the user token, refreshes it when it expires."""

    def __init__(
        self,
        *,
        scopes: tuple[str, ...] = CALENDAR_SCOPES,
        token_path: Path | None = None,
        flow_runner: FlowRunner | None = None,
    ) -> None:
        self._scopes = scopes
        self._token_path = token_path
        self._flow_runner = flow_runner

    def token(self) -> str:
        config = self._client_config()
        cached = self._cached()
        if cached is not None and cached.valid:
            return str(cached.token)
        if cached is not None and cached.refresh_token:
            refreshed = self._refresh(cached)
            if refreshed is not None:
                self._store(refreshed)
                return str(refreshed.token)
        fresh = self._run_flow(config)
        if not fresh.token:
            raise ToolError("the Google authorisation finished without an access token; authorise again")
        self._store(fresh)
        return str(fresh.token)

    def path(self) -> Path:
        return self._token_path if self._token_path is not None else default_token_path()

    def _client_config(self) -> Mapping[str, Any]:
        raw = os.environ.get(CREDENTIALS_ENV, "").strip()
        if not raw:
            raise ToolError(f"{CREDENTIALS_ENV} is not set; copy .env.example to .env and fill it in")
        source = Path(raw).expanduser()
        if source.is_file():
            try:
                text = source.read_text(encoding="utf-8")
            except OSError as exc:
                log.debug("client secrets unreadable", exc_info=True)
                raise ToolError(f"{CREDENTIALS_ENV} points at a file that cannot be read") from exc
        else:
            text = raw
        try:
            config = json.loads(text)
        except ValueError as exc:
            log.debug("client secrets not JSON", exc_info=True)
            raise ToolError(f"{CREDENTIALS_ENV} is neither a readable JSON file nor JSON itself") from exc
        if not isinstance(config, dict) or not ({"installed", "web"} & set(config)):
            raise ToolError(f"{CREDENTIALS_ENV} must hold a Google client secrets object with installed or web")
        return config

    def _cached(self) -> Credentials | None:
        path = self.path()
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.debug("no usable cached calendar token", exc_info=True)
            return None
        try:
            return Credentials.from_authorized_user_info(info, list(self._scopes))
        except ValueError:
            log.debug("cached calendar token is not in the authorized user format", exc_info=True)
            return None

    def _refresh(self, creds: Credentials) -> Credentials | None:
        from google.auth.transport.requests import Request

        try:
            creds.refresh(Request())
        except TransportError as exc:
            raise RetryableError("refreshing the Google Calendar token failed in transport") from exc
        except GoogleAuthError:
            log.debug("cached calendar token could not be refreshed, falling back to the flow", exc_info=True)
            return None
        return creds

    def _run_flow(self, config: Mapping[str, Any]) -> Credentials:
        runner = self._flow_runner if self._flow_runner is not None else _installed_app_flow
        try:
            return runner(config, self._scopes)
        except TransportError as exc:
            raise RetryableError("the Google authorisation flow failed in transport") from exc
        except GoogleAuthError as exc:
            log.debug("the Google authorisation flow failed", exc_info=True)
            raise ToolError("the Google authorisation flow failed; authorise again") from exc

    def _store(self, creds: Credentials) -> None:
        path = self.path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                out.write(creds.to_json())
            os.chmod(path, 0o600)
        except OSError as exc:
            log.debug("the calendar token cache could not be written", exc_info=True)
            raise ToolError(f"the Google Calendar token cache at {path} could not be written") from exc


def _installed_app_flow(config: Mapping[str, Any], scopes: tuple[str, ...]) -> Credentials:
    """The one interactive path. google-auth-oauthlib 1.4.1: from_client_config, then run_local_server."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_config(dict(config), scopes=list(scopes))
    creds = flow.run_local_server(port=0, open_browser=True)
    if not isinstance(creds, Credentials):
        raise ToolError("the Google authorisation returned a credential type the calendar cannot use")
    return creds
