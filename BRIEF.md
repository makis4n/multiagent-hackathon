# System and reliability brief

Submitted with the repo and the two-minute demo. Everything in here is reproducible from `main` at the SHA named
below: `make check` for the tests, `make fixture` for the seed trip, `make evals` for the table.

**SHA:** current `main` (refresh this line at the 15:00 freeze) · **Real tools at submission:** planner (Claude),
places and verifier (Google Places and Routes), research (YouTube and Exa scoped to reddit.com), booking (Duffel
test mode, flights). Calendar is the fake unless C4 lands.

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
| Google Calendar | the finished itinerary as events | fake unless C4 lands | C |

## 3. Failure modes

Each row names a test that plants the failure. A row without a test is a claim, not a mitigation.

| tool | failure | detected by | mitigation | test |
| --- | --- | --- | --- | --- |
| booking.order | provider 5xx after creating the order | `RetryableError` | one retry under the same idempotency key; the provider looks the key up first, so one order | `test_retry_keeps_exactly_one_order`, `test_injected_failure_recovers_with_one_order` |
| booking.order | called without user confirmation | `ToolError` | refused; the loop never calls it without `confirmed_by_user_at` | `test_order_refuses_unconfirmed`, `test_no_confirmation_means_no_order` |
| booking.order | live key in the environment | key prefix check | refused at client construction | Lane D, D2 |
| planner.draft | invented or unresolvable venue | `exists` check | stop marked failed, replaced from the signals or removed, recorded in `replacements` | `test_verifier_flags_the_closed_venue` |
| planner.draft | venue closed at the planned time | `open` check against Google hours | replacement pass, then prune | `test_fixture_runs_end_to_end`, `test_parse_place_maps_google_weekdays_onto_the_contract` |
| planner.draft | stops too far apart | `reachable` check, 45 min cap | two replacement passes, then prune until no leg fails | `test_stops_that_keep_failing_are_pruned_and_recorded`, `test_prune_repeats_when_a_removal_creates_a_new_failing_leg` |
| planner.draft | model puts a stop on a day that does not exist, or a bad time | conversion in code | dropped or repaired before anything sees it | `test_to_itinerary_repairs_what_the_model_got_wrong` |
| places | Google encodes "open 24 hours" as one closeless period | parser | every weekday marked open | `test_parse_place_open_24_hours_means_every_day` |
| places | no opening hours on record (areas, streets) | `is_open` returns None | check passes as "hours unknown" instead of failing | `test_parse_place_without_hours_is_unknown_not_closed` |
| routes | no transit route (this key returns none) | empty response | driving time × 1.2 plus five minutes, labelled in the check detail; straight line if that fails too | `test_verifier_falls_back_to_straight_line_when_routes_fails` |
| research.* | one source down or rate limited | `ToolError` from the source | the other sources still run, the failure is noted in the state, the draft proceeds; zero sources fails loudly | `test_one_dead_source_does_not_kill_the_run`, `test_no_source_at_all_fails_loudly` |
| model | 429, 5xx, overloaded (529) | `RetryableError` inside `complete_json` | four attempts, 3s/6s/9s backoff, then the stage fails loudly | `test_retries_a_busy_model_then_succeeds`, `test_gives_up_after_the_last_attempt` |
| model | answer does not match the schema | `SchemaError` in `complete_json` | one corrective retry with the validation errors in the prompt, then it propagates | `test_malformed_answer_gets_one_corrective_retry` |
| any tool | every call | `CallLog` | one JSONL line per attempt with latency and outcome, no request or response bodies; the evals and this brief read that log | `test_fixture_runs_end_to_end` (asserts the log) |

## 4. Eval results

`make evals` at af0f849, real planner, places and verifier; research and booking on fakes in this run
(`evals/results/af0f849.md`). Refresh at the freeze with every real flag on.

| trip | signals | resolved | verified | transit | bookable | gated | loop |
|---|---|---|---|---|---|---|---|
| bali | ✓ 16 signals, 16 places | ✓ 11/11 resolved | ✓ 100% of stops pass | ✓ worst leg 33 min of 45 | ✓ flight, stay | ✓ 2 orders, 2 keys | ✓ |
| bangkok | ✓ 16 signals, 16 places | ✓ 6/6 resolved | ✓ 100% of stops pass | ✓ worst leg 40 min of 45 | ✓ flight, stay | ✓ 2 orders, 2 keys | ✓ |
| barcelona | ✓ 16 signals, 16 places | ✓ 9/9 resolved | ✓ 100% of stops pass | ✓ worst leg 40 min of 45 | ✓ flight, stay | ✓ 2 orders, 2 keys | ✓ |
| copenhagen | ✓ 16 signals, 16 places | ✓ 12/12 resolved | ✓ 100% of stops pass | ✓ worst leg 29 min of 45 | ✓ flight, stay | ✓ 2 orders, 2 keys | ✓ |
| kyoto | ✓ 16 signals, 16 places | ✓ 11/11 resolved | ✓ 100% of stops pass | ✓ worst leg 28 min of 45 | ✓ flight, stay | ✓ 2 orders, 2 keys | ✓ |
| lisbon | ✓ 16 signals, 16 places | ✓ 12/12 resolved | ✓ 100% of stops pass | ✓ worst leg 42 min of 45 | ✓ flight, stay | ✓ 2 orders, 2 keys | ✓ |
| new-york | ✓ 16 signals, 16 places | ✓ 11/11 resolved | ✓ 100% of stops pass | ✓ worst leg 35 min of 45 | ✓ flight, stay | ✓ 2 orders, 2 keys | ✓ |
| seoul | ✓ 16 signals, 16 places | ✓ 11/11 resolved | ✓ 100% of stops pass | ✓ worst leg 41 min of 45 | ✓ flight, stay | ✓ 2 orders, 2 keys | ✓ |
| taipei | ✓ 16 signals, 16 places | ✓ 8/8 resolved | ✓ 100% of stops pass | ✓ worst leg 35 min of 45 | ✓ flight, stay | ✓ 2 orders, 2 keys | ✓ |
| tokyo | ✓ 18 signals, 18 places | ✓ 15/15 resolved | ✓ 100% of stops pass | ✓ worst leg 43 min of 45 | ✓ flight, stay | ✓ 2 orders, 2 keys | ✓ |
| **pass** | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 |

What the real run caught in Tokyo before the table was green: Nezu Museum and Tokyo National Museum both close on
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
- Model: switched from Gemini to Claude at 13:40 PT after the Gemini prepay balance ran out mid-afternoon; Gemini
  stays selectable with `LLM_PROVIDER=gemini`. Before that, free-tier quota forced Flash Lite for every call; the larger Flash models returned 503 on long
  structured prompts or ran out of quota within minutes.
- Calendar: fake unless Lane C's C4 lands before the freeze.
