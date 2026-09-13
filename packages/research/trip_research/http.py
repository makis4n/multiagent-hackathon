"""One status check for every provider. Rule 12: every third-party response checks its status.

A retryable status becomes httpx.HTTPError and anything else 4xx+ becomes ToolError, so a caller can tell a
"try again" from a "you are holding it wrong". The response body never reaches a log line.
"""

from __future__ import annotations

import httpx

from trip_core.models import ToolError

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def check_status(response: httpx.Response, provider: str) -> None:
    if response.status_code in RETRYABLE_STATUS:
        raise httpx.HTTPError(f"{provider} {response.status_code}")
    if response.status_code >= 400:
        raise ToolError(f"{provider} {response.status_code}")
