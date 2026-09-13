"""Lane D. Duffel flights and stays, activities, the confirmation gate behind one BookingProvider."""

from __future__ import annotations

import os

from trip_booking.duffel_client import DuffelClient
from trip_booking.provider import DuffelBookingProvider
from trip_core.models import ToolError
from trip_core.tools import BookingProvider

DUFFEL_TEST_PREFIX = "duffel_test_"


def build_provider() -> BookingProvider:
    """Duffel test mode behind it. Selected by REAL_BOOKING=1. Refuses a key that is not sandbox."""
    api_key = os.environ.get("DUFFEL_API_KEY")
    if not api_key or not api_key.startswith(DUFFEL_TEST_PREFIX):
        raise ToolError(f"DUFFEL_API_KEY must be a {DUFFEL_TEST_PREFIX} sandbox key")
    return DuffelBookingProvider(DuffelClient(api_key))
