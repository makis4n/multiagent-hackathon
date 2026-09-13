# Lane D plan: D2 to D4, from 13:30 to the 15:00 freeze

D1 is merged (#16): search works, ZZ-first stable sort, five options max, 5xx and 429 raise `RetryableError`,
the sandbox-key prefix is enforced in `build_provider`. D3 (activities, budget guard) is cut. What is left is
`order()` and the proof that it is safe. Ninety minutes: D2 by 14:15, D4 by 14:40, brief rows by 14:50.

| step | issue | done when |
| --- | --- | --- |
| D2 `order()` | #9 | `REAL_BOOKING=1 INJECT_BOOKING_FAILURE=1 make fixture` prints one Duffel order reference; the three gate tests pass against the real client with cassettes |
| D4 recovery test | #11 | a recorded create-then-lost-response run ends with exactly one order; brief rows filled |

## D2: `order(option, idempotency_key, confirmed_by_user_at) -> BookingOrder`

The loop calls this once per confirmed option, through `CallLog.call(..., retries=1)`, and the demo's
`INJECT_BOOKING_FAILURE=1` wrapper calls it, lets it complete, raises, and calls it **again with the same key**.
So the method has to be safe to call twice.

Order of operations, and none of it is optional:

1. **Refuse without confirmation.** `confirmed_by_user_at is None` raises `ToolError`. The type says datetime;
   the runtime guard stays, the fake has the same line.
2. **Look the key up first.** Keep a small store keyed by idempotency key: a JSON file under `logs/orders.json`
   (gitignored) is enough today. If the key is there, return the stored `BookingOrder` and make no request.
3. **Then the provider-side check.** If the key is not stored locally, list recent orders from Duffel
   (`GET /air/orders`, newest first, first page) and scan `metadata.idempotency_key`. A hit means the create
   succeeded but the response was lost: adopt it, store it, return it. This is the case the injected failure
   simulates and the case D4 proves.
4. **Create.** `POST /air/orders` with `selected_offers: [option.provider_ref]`, `passengers` built from the offer
   request's passenger ids (the offer carries `passengers[].id`; keep them in `option.details` at search time,
   it is the cleanest place), fixed test identities (`given_name`, `family_name`, `born_on`, `gender`, `title`,
   `email`, `phone_number`, one per traveller), `payments: [{"type": "balance", "amount": offer.total_amount,
   "currency": offer.total_currency}]`, and `metadata: {"idempotency_key": idempotency_key, "brief_id": ...}`.
   Store the result under the key **before** returning.
5. **Map the result.** `BookingOrder(id=f"ord_{key[:10]}", option=option, idempotency_key=key,
   confirmed_by_user_at=..., status=confirmed, provider_order_id=data["booking_reference"],
   receipt={"duffel_order_id": data["id"], "total_minor": ..., "currency": ...})`. The booking reference is what
   the demo shows on screen.

Failure mapping, same as search: 5xx, 429, timeout raise `RetryableError`; 401, 403, 404 raise `ToolError`.
Two 422s deserve their own messages because they will happen in the demo: an expired offer (Duffel offers live
minutes; say "offer expired, search again") and insufficient balance on the test account (say so; the balance is
topped up in the Duffel dashboard).

Tests, copied from `packages/core/tests/test_fakes.py` and pointed at the real provider with a
`httpx.MockTransport` or the cassette helper:

- `test_order_refuses_unconfirmed`: no request is made.
- `test_order_is_idempotent`: second call with the same key returns the stored order, makes no request.
- `test_a_live_key_is_rejected` already exists; keep it.

Cassette: one real create in the sandbox (trim to the fields the mapping reads), one real orders list.

## D4: the lost-response proof

The failure the brief promises to survive: the provider created the order, the response never arrived, the
loop retries under the same key. Test it with a transport that returns the recorded create response, then on the
next `order()` call with the same key returns the recorded orders list containing that order's metadata. Assert:
one create request, one order in the store, the same `provider_order_id` both times. Then run
`REAL_BOOKING=1 INJECT_BOOKING_FAILURE=1 make fixture` and paste the output line into the PR.

Fill these rows in `BRIEF.md` with the test names: "live key in the environment", and add one row for "offer
expired between search and order".

## Handoff

PR per step, non-draft the moment `make check` is green, closes the issue, `D: LIVE — <flag, command>` in chat.
Keep the cassettes small: three offers, one order, one list page. `logs/` is gitignored; do not commit the order
store.
