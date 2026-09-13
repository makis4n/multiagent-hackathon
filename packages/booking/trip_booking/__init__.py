"""Lane D. Duffel flights and the confirmation gate behind one BookingProvider. Stays and activities are cut."""

from __future__ import annotations

import os
from pathlib import Path

from trip_booking.duffel_client import DuffelClient
from trip_booking.provider import DEFAULT_STORE, DuffelBookingProvider, OrderStore
from trip_core.models import ToolError
from trip_core.tools import BookingProvider

DUFFEL_TEST_PREFIX = "duffel_test_"


def build_provider(store_path: Path | None = None) -> BookingProvider:
    """Duffel test mode behind it. Selected by REAL_BOOKING=1. Refuses a key that is not sandbox. Orders are
    remembered in ORDER_STORE (default logs/orders.json, gitignored) so a retry in a new process finds them."""
    api_key = os.environ.get("DUFFEL_API_KEY")
    if not api_key or not api_key.startswith(DUFFEL_TEST_PREFIX):
        raise ToolError(f"DUFFEL_API_KEY must be a {DUFFEL_TEST_PREFIX} sandbox key")
    path = store_path or Path(os.environ.get("ORDER_STORE") or DEFAULT_STORE)
    return DuffelBookingProvider(DuffelClient(api_key), OrderStore(path))
