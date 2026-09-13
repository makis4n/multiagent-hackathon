# System and reliability brief

Submitted with the repo and the two-minute demo. Everything in here is reproducible from `main` at the SHA named
below: `make check` for the tests, `make fixture` for the seed trip, `make evals` for the table.

**Code SHA:** `ef032b7` (commits after it on `main` are documentation) · **Real tools at submission:** planner
(Claude), places and verifier (Google Places and Routes), research (YouTube and Exa scoped to reddit.com), booking
(Duffel test mode, flights). Calendar is the fake; it was cut.

## 1. What it does

A traveller gives a destination, dates, party size, a budget band and a few style words, then answers up to four
questions. They get a day-by-day itinerary in which every stop cites the recent post it came from, has been
checked against Google for existence, opening hours at the planned time and travel time from the previous stop,
and a flight booked in Duffel's sandbox only after they click. In between, the agent researches what people
posted recently, drafts with Claude, turns the answers into patches rather than a rewrite, verifies every stop,
swaps or drops what fails and says why, and never places an order without an explicit confirmation.

Loop: brief → research → draft → questions → patches → resolve → verify → up to two replacement passes → prune
until stable → book behind a confirmation → calendar. The loop is code; the model only fills typed slots. See
`ARCHITECTURE.md`.

## 2. External apps

| app | used for | mode | lane |
| --- | --- | --- | --- |
| YouTube Data API | recent vlogs for the destination → signals | live, read only | B |
| Exa | web search scoped to reddit.com → signals (Reddit's own API is written but unwired: their policy needs approval) | live, read only | B |
| Google Places API (New) | resolve every stop, opening hours, coordinates | live, read only | C (built by A) |
| Google Routes API | travel time between consecutive stops | live, read only | C (built by A) |
| Claude (anthropic SDK) | drafting, questions, replacements, signal extraction | live, Sonnet 5 main and Haiku 4.5 fast; Gemini Flash Lite kept behind `LLM_PROVIDER=gemini` | A, C |
| Duffel | flight search and orders | **test mode only**; the client refuses a live key | D |
| Google Calendar | the finished itinerary as events | fake; cut for the day | C |

## 3. Failure modes

Each row names a test that plants the failure. A row without a test is a claim, not a mitigation.

| tool | failure | detected by | mitigation | test |
| --- | --- | --- | --- | --- |
| booking.order | provider 5xx after creating the order | `RetryableError` | one retry under the same idempotency key; the provider looks the key up first, so one order | `test_retry_keeps_exactly_one_order`, `test_injected_failure_recovers_with_one_order`, `test_order_is_idempotent` (Duffel) |
| booking.order | called without user confirmation | `ToolError` | refused; the loop never calls it without `confirmed_by_user_at` | `test_order_refuses_unconfirmed`, `test_no_confirmation_means_no_order` |
| booking.order | live key in the environment | key prefix check | refused before a client exists | `test_a_live_key_is_rejected` |
| booking.order | Duffel created the order, the response never arrived | timeout, `RetryableError` | the retry lists Duffel orders and adopts the one carrying its idempotency key; one create request, one order | `test_lost_create_response_recovers_from_the_provider` |
| booking.order | offer expired between search and order | Duffel 422 `offer_no_longer_available` | `ToolError` "offer expired, search again"; nothing stored | `test_an_expired_offer_says_search_again` |
| booking.order | sandbox balance exhausted | Duffel 422 `insufficient_balance` | `ToolError` naming the cause, so the demo does not read it as a bug | `test_insufficient_balance_says_so` |
| booking.order | process restarts between the order and the retry | file-backed order store | the new process reads `logs/orders.json` and returns the order without a request | `test_the_store_survives_a_new_process` |
| planner.draft | invented or unresolvable venue | `exists` check | stop marked failed, replaced from the signals or removed, recorded in `replacements` | `test_verifier_flags_the_closed_venue` |
| planner.draft | venue closed at the planned time | `open` check against Google hours | replacement pass, then prune | `test_fixture_runs_end_to_end`, `test_parse_place_maps_google_weekdays_onto_the_contract` |
| planner.draft | stops too far apart | `reachable` check, 45 min cap | two replacement passes, then prune until no leg fails | `test_stops_that_keep_failing_are_pruned_and_recorded`, `test_prune_repeats_when_a_removal_creates_a_new_failing_leg` |
| planner.draft | model puts a stop on a day that does not exist, or a bad time | conversion in code | dropped or repaired before anything sees it | `test_to_itinerary_repairs_what_the_model_got_wrong` |
| places | Google encodes "open 24 hours" as one closeless period | parser | every weekday marked open | `test_parse_place_open_24_hours_means_every_day` |
| places | no opening hours on record (areas, streets) | `is_open` returns None | check passes as "hours unknown" instead of failing | `test_parse_place_without_hours_is_unknown_not_closed` |
| routes | no transit route (this key returns none) | empty response | driving time × 1.2 plus five minutes, labelled in the check detail; straight line if that fails too | `test_verifier_falls_back_to_straight_line_when_routes_fails` |
| research.* | one source down or rate limited | `ToolError` from the source | the other sources still run, the failure is noted in the state, the draft proceeds; zero sources fails loudly | `test_one_dead_source_does_not_kill_the_run`, `test_no_source_at_all_fails_loudly` |
| model | 429, 5xx, overloaded (529) | `RetryableError` inside `complete_json` | four attempts, 3s/6s/9s backoff, then the stage fails loudly | `test_retries_a_busy_model_then_succeeds`, `test_gives_up_after_the_last_attempt` |
| model | answer does not match the schema | `SchemaError` in `complete_json` | one corrective retry with the validation errors in the prompt, then it propagates | `test_malformed_answer_gets_one_corrective_retry`, `test_claude_wrong_shape_is_a_schema_error` |
| model | nested list returned as a JSON string inside the JSON (seen live with a forced tool call) | `SchemaError` | the schema is sent as a structured output format with constrained decoding instead of a tool; `additionalProperties: false` on every object | `test_claude_answers_in_the_schema` |
| any tool | every call | `CallLog` | one JSONL line per attempt with latency and outcome, no request or response bodies; the evals and this brief read that log | `test_fixture_runs_end_to_end` (asserts the log) |

## 4. Eval results

Seven checks per brief, ten briefs, read from the call log and the final state: enough signals and places, every
stop resolved, at least 90% of stops verified, no leg over the transit cap, a bookable flight, every order behind
a confirmation with a distinct key, and the loop finishing. Earlier tables: `evals/results/af0f849.md` (real
planner, places, verifier; fakes elsewhere), `evals/results/04bc720.md` (real research added; four briefs lost a
signal point to one dead link among ten sampled, before the check allowed one).

`make evals` at `ef032b7`, 14:17 PT, every real flag on: research, planner, places, verifier and booking, with
the booking failure injected on the first order. Ten real Duffel sandbox orders, one per brief, one key each
(`evals/results/ef032b7.md`, call log `logs/evals-ef032b7.jsonl`). Runtime 15 minutes, briefs run one after another.

| trip | signals | resolved | verified | transit | bookable | gated | loop |
|---|---|---|---|---|---|---|---|
| bali | ✓ 100 signals, 97 places, 0 dead of 10 URLs checked | ✓ 22/22 resolved | ✓ 100% of stops pass | ✓ worst leg 43 min of 45 | ✓ flight | ✓ 1 orders, 1 keys | ✓ |
| bangkok | ✓ 100 signals, 106 places, 0 dead of 10 URLs checked | ✓ 12/12 resolved | ✓ 100% of stops pass | ✓ worst leg 42 min of 45 | ✓ flight | ✓ 1 orders, 1 keys | ✓ |
| barcelona | ✓ 98 signals, 86 places, 0 dead of 10 URLs checked | ✓ 20/20 resolved | ✓ 100% of stops pass | ✓ worst leg 45 min of 45 | ✓ flight | ✓ 1 orders, 1 keys | ✓ |
| copenhagen | ✓ 98 signals, 67 places, 0 dead of 10 URLs checked | ✓ 10/10 resolved | ✓ 100% of stops pass | ✓ worst leg 32 min of 45 | ✓ flight | ✓ 1 orders, 1 keys | ✓ |
| kyoto | ✓ 98 signals, 78 places, 0 dead of 10 URLs checked | ✓ 28/28 resolved | ✓ 100% of stops pass | ✓ worst leg 45 min of 45 | ✓ flight | ✓ 1 orders, 1 keys | ✓ |
| lisbon | ✓ 98 signals, 79 places, 1 dead of 10 URLs checked | ✓ 12/12 resolved | ✓ 100% of stops pass | ✓ worst leg 16 min of 45 | ✓ flight | ✓ 1 orders, 1 keys | ✓ |
| new-york | ✓ 100 signals, 92 places, 0 dead of 10 URLs checked | ✓ 12/12 resolved | ✓ 100% of stops pass | ✓ worst leg 25 min of 45 | ✓ flight | ✓ 1 orders, 1 keys | ✓ |
| seoul | ✓ 99 signals, 83 places, 1 dead of 10 URLs checked | ✓ 20/20 resolved | ✓ 100% of stops pass | ✓ worst leg 42 min of 45 | ✓ flight | ✓ 1 orders, 1 keys | ✓ |
| taipei | ✓ 99 signals, 88 places, 1 dead of 10 URLs checked | ✓ 9/9 resolved | ✓ 100% of stops pass | ✓ worst leg 38 min of 45 | ✓ flight | ✓ 1 orders, 1 keys | ✓ |
| tokyo | ✓ 100 signals, 100 places, 0 dead of 10 URLs checked | ✓ 18/18 resolved | ✓ 100% of stops pass | ✓ worst leg 37 min of 45 | ✓ flight | ✓ 1 orders, 1 keys | ✓ |
| **pass** | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 |

What the real runs caught in Tokyo before the table was green: Nezu Museum and Tokyo National Museum both close on
Mondays and were dropped from the Monday slot; Kappabashi's shops were closed at the planned Saturday hour; a
Yoyogi Park to Kiyosumi Gardens leg was 55 minutes. All four appear in the state's `replacements` with the reason.

## 5. Known gaps and what was cut

- TikTok: no usable API. YouTube and reddit.com content through Exa carry the social signal instead.
- Reddit's own API: implemented and tested, deliberately not wired; their Responsible Builder Policy requires
  approval we do not have. Reddit content still arrives through Exa's reddit.com-scoped search.
- Activity tickets: cut. No purchase API at affiliate tier; the flight is the booking the demo shows.
- Stays: Duffel Stays needs a commercial agreement ("contact sales"), so stays exist on the fake provider only and
  the bookable eval row is scoped to flights.
- Real payment: Duffel test mode only, by design, all day.
- Transit: Google Routes returns no transit route on our key, so travel time is a driving-based estimate labelled
  as such. It is conservative in rail-heavy cities and the 45-minute cap is applied to it as-is.
- Model: Gemini until 13:40 PT, when its prepay balance ran out (the $300 Cloud trial credit excludes the Gemini
  API). Claude replaced it in one file, `trip_core/llm.py`, with the same typed contract; Gemini stays selectable
  with `LLM_PROVIDER=gemini`. The first Claude version used a forced tool call and the model twice returned a nested
  list as a string; structured outputs with constrained decoding fixed it.
- Latency: on Claude Sonnet 5 at low effort a draft takes about 22 s (Gemini Flash Lite: 7 s); research 28 s,
  questions 4 s, a replacement pass 6 s, the whole verification loop about 40 s. A full real run is around two
  minutes and the demo narrates the two waits.
- Calendar: fake. C4 was cut so the verification and booking paths got the time.
- Refinement: the answers-to-patches step is rule based (`skip: <place>`); a model-backed version is issue #14.

## 6. Reproduce

```sh
uv sync --all-packages && cp .env.example .env     # fill the keys named in README.md
make check                                          # 139 tests, offline
make fixture                                        # the seed trip on fakes
REAL_RESEARCH=1 REAL_PLANNER=1 REAL_PLACES=1 REAL_VERIFIER=1 REAL_BOOKING=1 INJECT_BOOKING_FAILURE=1 make fixture
make evals                                          # writes evals/results/<sha>.md
```

The last fixture line prints the real tools used, `booking failure injected`, and the Duffel booking reference.
`logs/calls.jsonl` holds one line per tool call; `logs/orders.json` holds every order by idempotency key.
