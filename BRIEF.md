# System and reliability brief

Submitted with the repo and the two-minute demo. Lane A owns the document; every lane fills its own rows by 15:00 PT.
Everything in here must be reproducible from `main` at the SHA named below.

**SHA:** `<fill at freeze>` · **Real tools at submission:** `<research, places, planner, verifier, booking, calendar>`

## 1. What it does

<Three sentences. What the traveller gives, what they get, what the agent does in between.>

Loop: brief → research → draft → questions → patches → resolve → verify → one replacement pass → book (behind a
confirmation) → calendar. See `ARCHITECTURE.md`.

## 2. External apps

| app | used for | mode | lane |
| --- | --- | --- | --- |
| Reddit | destination subreddits and r/travel → signals | live, read only | B |
| YouTube Data API | recent vlogs and transcripts → signals | live, read only | B |
| Google Places (New) | resolve every stop, opening hours | live, read only | C |
| Google Routes | transit time between consecutive stops | live, read only | C |
| Google Calendar | the finished itinerary as events | live, writes to one test calendar | C |
| Duffel | flight and stay search and orders | **test mode only**; the client refuses a live key | D |
| Gemini | drafting, refinement, signal scoring | live | A/C |

## 3. Failure modes

Each row names a test that plants the failure. A row without a test is a claim, not a mitigation.

| tool | failure | detected by | mitigation | test |
| --- | --- | --- | --- | --- |
| booking.order | provider 5xx after creating the order | `RetryableError` | one retry under the same idempotency key; provider looks the key up first | `test_retry_keeps_exactly_one_order` |
| booking.order | called without user confirmation | `ToolError` | refused; the loop never calls it without `confirmed_by_user_at` | `test_order_refuses_unconfirmed` |
| booking.order | live key in the environment | key prefix check | refused at client construction | <D> |
| planner.draft | invented venue | `exists` check | stop marked failed, one replacement pass | `test_verifier_flags_the_closed_venue` |
| planner.draft | venue closed at the planned time | `open` check | replacement pass | `test_fixture_runs_end_to_end` |
| planner.draft | stops too far apart | `reachable` check, 45 min cap | replacement pass | <C> |
| research.* | source down or rate limited | `ToolError` from the source | the other sources still run, the failure is noted in the state, the draft proceeds with fewer signals; zero sources fails loudly | `test_one_dead_source_does_not_kill_the_run` |
| gemini | 429/5xx, model overloaded | `RetryableError` inside `complete_json` | three attempts, 2s/4s backoff, then the stage fails loudly | `test_retries_a_busy_model_then_succeeds` |
| gemini | answer does not match the schema | `SchemaError` in `complete_json` | one corrective retry with the validation errors in the prompt, then it propagates | `test_malformed_answer_gets_one_corrective_retry` |

## 4. Eval results

Paste `evals/results/<sha>.md` for the submission SHA here. Ten briefs; columns signals, resolved, verified,
transit, bookable, gated, loop.

## 5. Known gaps and what was cut

- <TikTok: no usable API; Reddit and YouTube carry the social signal instead.>
- <Activity tickets: search and deep link only; no purchase API at affiliate tier.>
- <Real payment: Duffel test mode only.>
- <Anything cut at 14:00 per the plan's cut order.>
