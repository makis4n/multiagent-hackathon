"""Thin httpx wrapper over Duffel's Offer Requests and Orders APIs, sandbox only.

Rule 12: every third-party response checks its status. A retryable status or transport failure becomes
RetryableError, anything else 4xx+ becomes ToolError. The response body never reaches an error message; a 422
carries only Duffel's error code, so "offer expired" and "insufficient balance" read as what they are.
"""

from __future__ import annotations

from typing import Any

import httpx

from trip_core.models import RetryableError, ToolError

BASE_URL = "https://api.duffel.com"
DUFFEL_VERSION = "v2"
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
ORDERS_PAGE = 50
ERROR_MESSAGES = {
    "offer_no_longer_available": "offer expired between search and order; search again",
    "offer_request_expired": "offer expired between search and order; search again",
    "insufficient_balance": "insufficient balance on the Duffel test account; top it up in the dashboard",
}


class DuffelClient:
    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._client = client if client is not None else httpx.Client(timeout=20.0)

    def create_offer_request(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/air/offer_requests", json=body)

    def create_order(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/air/orders", json=body)

    def list_orders(self, limit: int = ORDERS_PAGE) -> list[dict[str, Any]]:
        """The first page, newest first: enough to find an order created seconds ago whose response was lost."""
        payload = self._request("GET", "/air/orders", params={"limit": limit})
        orders = payload.get("data")
        if not isinstance(orders, list):
            raise ToolError("duffel returned a non-list orders page")
        return [order for order in orders if isinstance(order, dict)]

    def _request(
        self, method: str, path: str, *, json: dict[str, Any] | None = None, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            response = self._client.request(
                method,
                f"{BASE_URL}{path}",
                json=json,
                params=params,
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
        if response.status_code == 422:
            raise ToolError(f"duffel 422: {describe_422(response)}")
        if response.status_code >= 400:
            raise ToolError(f"duffel {response.status_code}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ToolError("duffel returned a non-object body")
        return payload


def describe_422(response: httpx.Response) -> str:
    """Only Duffel's error code leaves the body, never its message or the request that caused it."""
    try:
        errors = response.json().get("errors") or []
    except ValueError:
        return "unprocessable request"
    codes = [str(error.get("code", "")) for error in errors if isinstance(error, dict)]
    for code in codes:
        if code in ERROR_MESSAGES:
            return ERROR_MESSAGES[code]
    return ", ".join(code for code in codes if code) or "unprocessable request"
