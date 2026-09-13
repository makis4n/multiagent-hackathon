# Architecture

One agent, one loop, six Protocols, three lanes of real implementations behind flags. The loop is code; the model
only fills typed slots inside the planner. That is what makes the run reproducible enough to evaluate.

## The loop (`apps/agent/trip_agent/loop.py`)

```
TripBrief
  -> research      every ResearchSource.search(brief)            -> Signal[]  (deduped by URL, best first)
  -> draft         ItineraryPlanner.draft(brief, signals)          -> Itinerary v1
  -> refine        ItineraryPlanner.questions(...) -> ask the user -> ItineraryPlanner.refine(...) -> patches
  -> resolve       resolve_places(itinerary, PlaceResolver)        -> place_id on every stop
  -> verify        Verifier.verify(itinerary)                      -> VerificationReport (exists, open, reachable, in_window)
  -> replace       one pass: ItineraryPlanner.replace_failed(...)  -> patches, then resolve + verify again
  -> book          BookingProvider.search(brief, kind) -> confirm(option) -> BookingProvider.order(option, key, at)
  -> calendar      CalendarSink.export(itinerary, brief)           -> URL
  -> TripState
```

Every stage call goes through `CallLog.call`, which writes one JSONL line per attempt and retries a
`RetryableError` once where the loop asks for it (booking orders). Patches are the only way an itinerary changes
after the draft: `apply_patch` is pure and bumps the version, so every itinerary the user saw is reconstructible.

## The contract (`packages/core`)

`trip_core.models` holds the types, `trip_core.tools` the Protocols, `trip_core.fakes` a deterministic fake for
each. The fixture trip (`trip_core/fixtures/tokyo.json`, a brief plus 18 signals) runs end to end on fakes with
`make fixture`. Real implementations replace fakes one flag at a time (`REAL_RESEARCH=1`, ...), which is how the
lanes integrate without waiting for each other.

## Money and safety

Nothing is ordered without `confirmed_by_user_at`. Every order carries an idempotency key derived from the brief and
the offer; the provider looks it up before creating anything, so a retry after a lost response never creates a
second order. Booking runs in Duffel test mode only; the client refuses a live key. The fakes encode all three rules
and the tests in `packages/core/tests/test_fakes.py` prove them.

## Model

Gemini through `trip_core.llm.complete_json(prompt, Schema)`: JSON mode with a flat pydantic response schema.
`GEMINI_MODEL_MAIN` (default gemini-flash-latest) for drafting and refinement, `GEMINI_MODEL_FAST` (default
gemini-flash-lite-latest) for scoring and extraction. Transport and rate-limit failures surface as `RetryableError`.

## Evals

`evals/trips` holds ten briefs. `make evals` runs each through the loop with the active flags and writes
`evals/results/<sha>.md`: signals, resolved, verified, transit, bookable, gated, loop, per trip and in total. The
reliability brief quotes that table for the head SHA.
