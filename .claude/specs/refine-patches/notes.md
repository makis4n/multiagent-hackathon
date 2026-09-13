# Ledger: refine-patches

Issue #14. Branch `lane/c-refine-patches`.

| task | commit | verdict | note |
| --- | --- | --- | --- |
| 1 claim the lane | 50d30f6 | done, orchestrator | one line, no dispatch |
| 2 flat schemas and mapping | 88f2865 | pass with notes | see below |

## Task 2 notes, carried forward

1. **For task 4.** `Itinerary.locate` raises `KeyError`, not `ValueError` (`packages/core/trip_core/models.py:140`).
   The mapping checks stop ids against the itinerary as passed in, so a payload that removes a stop and then moves
   the same stop still reaches `apply_patch` and raises `KeyError`. Task 4's filter catches `KeyError` alongside
   `ValueError`, or tests each candidate against a fresh copy. The spec's failure table names only `ValueError`.
2. `category` and `why` are required strings with no minimum length, so an empty string satisfies the schema.
   Behaviour 6 is shape-only at this layer.
3. `test_schemas.py:41` asserts on the field list rather than on behaviour. Harmless, guards against a dict field.
4. `OPS` reads the `op` Literal out of the contract, which keeps it in sync but would go quietly empty if core
   ever stopped using a Literal. A test pinning the four ops would catch that.

The reviewer mutation-tested the seven tests from a copy outside the repo: removing each guard turns its test red.

| 3 questions | 60db99e | pass with notes | six guards mutation-proven red |

## Task 3 notes, carried forward

1. **Spec correction, made by the orchestrator before task 4.** Behaviour 7 said the count of dropped patches goes
   into the itinerary notes, which `refine` cannot do: it returns patches and never an `Itinerary`. Behaviour 7 and
   10 and two table rows now record drops in `last_dropped` on the planner instead. No behaviour was weakened.
2. **For task 5.** Behaviour 10 covers `questions` as well as `refine`, and the spec's test table only named the
   refine one. A `test_model_failure_returns_no_questions` is now in the spec and task 5 owes both.
3. **For task 5.** `QuestionsResponse.questions` uses `default_factory=list`, so a payload that omits the field
   validates to an empty list rather than raising. The "output that does not validate" test must plant something
   that really fails validation.
4. **For task 4.** There is no `conftest.py` guarding against an un-stubbed `complete_json`. With three more test
   files arriving, one forgotten stub becomes a live model call rather than a test failure. Task 4 adds an autouse
   fixture that raises on any un-stubbed call.
5. `test_skips_answered_questions` carries the blank guard, the dedupe guard and the answered filter at once. A
   regression in any of the three reports as the same failure. Worth splitting when someone is next in that file.
