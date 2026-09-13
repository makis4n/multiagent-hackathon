# trip-booking

Status: **KieronOei**.

Lane D. Duffel test mode for flights and stays, Viator or Amadeus for activity search. Implement
`build_provider()` in `trip_booking/__init__.py`; `REAL_BOOKING=1` selects it.

Non-negotiable, and each one has a test in `trip_core/tests/test_fakes.py` to copy:

- `order()` refuses a call without `confirmed_by_user_at`.
- `order()` looks the idempotency key up before creating anything; a retry never creates a second order.
- The client asserts the Duffel key starts with `duffel_test_` and refuses anything else.
