# Cassettes

Recorded Duffel sandbox responses. Tests replay these through respx; CI never opens a socket.

## What was verified live, against a real `duffel_test_` key, 2026-09-13

| Finding | Result |
|---|---|
| `POST https://api.duffel.com/air/offer_requests`, headers `Authorization: Bearer <key>`, `Duffel-Version: v2`, body `{"data": {"passengers": [{"type": "adult"}], "slices": [{"origin", "destination", "departure_date"}]}}` | Works. `201`, `data.offers[]` populated. |
| `data.offers[].total_amount` / `total_currency` | Decimal string (`"977.28"`), ISO currency code (`"EUR"`). |
| `data.offers[].owner.iata_code` | Two-letter IATA code; Duffel's own sandbox test airline is `ZZ` ("Duffel Airways"), mixed in with real carriers (`BA`, `LH`, `JL`, ...) at random prices. |
| Sandbox inventory | Not stable between calls: same request, different offers and prices each time. `flights_search.json` and `flights_search_zz.json` are single recordings, hand-trimmed to three offers each, not reproducible by re-running the request. |

`flights_search_zz.json` keeps a `ZZ` offer that is not the cheapest of its three, so a test can prove the
ZZ-first bias beats price. `flights_search.json` has no `ZZ` offer at all and is ordered most-expensive-first
in the file, so a test can prove the price sort is not a no-op.

## Order cassettes

`order_create.json` and `orders_list.json` are shaped from Duffel's order object (`data.id`, `booking_reference`,
`total_amount`, `total_currency`, `metadata`) as documented at duffel.com/docs, trimmed to the fields
`DuffelBookingProvider._to_order` reads. `REPLACED_BY_TEST` is stamped with the test's own idempotency key. The
live proof of the same path is `REAL_BOOKING=1 INJECT_BOOKING_FAILURE=1 make fixture` against the sandbox.

## What was assumed, not verified

- Duffel Stays and the activities search: no commercial agreement on this sandbox account, so both are
  unverified against real Duffel endpoints. `DuffelBookingProvider.search` returns `[]` for both kinds without
  a request.
