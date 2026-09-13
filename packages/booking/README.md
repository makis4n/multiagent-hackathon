# trip-booking

Status: **KieronOei** (D1 search), **Wai Kin** (D2 order, D4 recovery). D3 cut.

Lane D. Duffel test mode for flights; stays and activities return no options. `build_provider()` in
`trip_booking/__init__.py`; `REAL_BOOKING=1` selects it. Orders are remembered by idempotency key in
`ORDER_STORE` (default `logs/orders.json`, gitignored); a retry finds them there, then in Duffel's own order list.

Non-negotiable, and each one has a test in `trip_core/tests/test_fakes.py` to copy:

- `order()` refuses a call without `confirmed_by_user_at`.
- `order()` looks the idempotency key up before creating anything; a retry never creates a second order.
- The client asserts the Duffel key starts with `duffel_test_` and refuses anything else.
