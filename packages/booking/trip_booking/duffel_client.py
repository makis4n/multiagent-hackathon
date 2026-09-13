"""Thin httpx wrapper over Duffel's Offer Requests API, sandbox only.

Rule 12: every third-party response checks its status. A retryable status or transport failure becomes
RetryableError, anything else 4xx+ becomes ToolError. The response body never reaches an error message.
"""

from __future__ import annotations

from typing import Any

import httpx

from trip_core.models import RetryableError, ToolError

BASE_URL = "https://api.duffel.com"
DUFFEL_VERSION = "v2"
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class DuffelClient:
    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._client = client if client is not None else httpx.Client(timeout=10.0)

    def create_offer_request(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/air/offer_requests", body)

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(
                f"{BASE_URL}{path}",
                json=body,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Duffel-Version": DUFFEL_VERSION,
                    "Content-Type": "application/json",
                },
            )
        except httpx.HTTPError as error:
            raise RetryableError(f"duffel: {type(error).__name__}") from error
        if response.status_code in RETRYABLE_STATUS:
            raise RetryableError(f"duffel {response.status_code}")
        if response.status_code >= 400:
            raise ToolError(f"duffel {response.status_code}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ToolError("duffel returned a non-object body")
        return payload
