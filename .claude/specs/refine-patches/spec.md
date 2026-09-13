# Refinement: questions in, patches out

Lane C, `packages/itinerary`. Branch `lane/c-refine-patches`. Flag `REAL_PLANNER`. Issue #14.

## Goal
The agent asks the traveller at most four questions it does not already have answers to, and turns each answer
into a small set of patches applied to the itinerary, so a refinement edits the plan the user already saw
instead of replacing it with a new one.

## Contract impact
None. `ItineraryPlanner`, `ItineraryPatch`, `apply_patch` and `MAX_QUESTIONS` all exist in `trip_core`, the
`REAL_PLANNER` flag exists, and `registry.py` already calls `build_planner()`. No edit to `packages/core` and no
edit to Lane A's files.

`build_planner()` returns a planner whose `questions`, `refine` and `replace_failed` are model-backed and whose
`draft` delegates to `trip_core.fakes.FakePlanner`, until the draft is specced separately. The package README
table says so in the same commit, so nobody reads a fake draft as a real one.

`packages/itinerary/pyproject.toml` gains no new runtime dependency: `complete_json` already lives in `trip_core`.

## Behaviour

`ItineraryPlanner.questions(brief, itinerary)`:

1. Returns at most `MAX_QUESTIONS` questions, and fewer when the brief has fewer gaps. Never a question whose
   text is already a key in `brief.answers`.
2. Each question is one sentence about a gap the brief leaves open, answerable in a few words, and about this
   itinerary rather than travel in general. The model fills a flat schema of strings; the cap is applied in code
   after the call, never trusted to the prompt.

`ItineraryPlanner.refine(brief, itinerary, answers, signals)`:

3. Returns `list[ItineraryPatch]` and nothing else. It never returns an `Itinerary`, and the loop stays the only
   thing that applies a patch.
4. Every returned patch applies cleanly. Candidates are applied in order onto an accumulating copy with
   `apply_patch`, so a later patch may depend on an earlier one; one that raises `ValueError` or `KeyError` is
   dropped with its reason recorded, never returned and never raised.
5. `remove`, `move` and `replace` name a `stop_id` that exists in the itinerary. `add` carries a stop whose id is
   not already in use and a `target_day` inside the itinerary.
6. A stop the model adds or substitutes in carries a category, a one-sentence `why`, and `signal_ids` that are a
   subset of the ids actually passed in. An id the signals do not contain is stripped rather than invented.
7. At most eight patches come back from one refinement round. Beyond that it is a regeneration wearing a patch
   costume, so the extras are dropped and counted in `last_dropped` on the planner. `refine` returns patches and
   nothing else, so a dropped patch is recorded on the planner rather than written into the itinerary.

`ItineraryPlanner.replace_failed(brief, itinerary, report, signals)`:

8. Emits exactly one patch per id in `report.failed_stop_ids()` and touches no other stop: a `replace` keeping
   the original day and time slot when a candidate place is available, otherwise a `remove`.
9. A replacement never reuses a place already in the itinerary, and never a place an answer marked `skip:`.

Both model-backed paths:

10. A model failure degrades to no change: `RetryableError` or `ToolError` out of `complete_json`, or output that
    does not validate, returns an empty patch list and records the reason in `last_dropped`. `questions` degrades
    the same way, to no questions. The traveller keeps the itinerary they
    were already looking at, and the run continues to resolve, verify and book.

## Failure handling

| Call | Failure | Detected by | What the code does |
| --- | --- | --- | --- |
| `complete_json` in `questions` | 429, 5xx, timeout | `RetryableError` | returns no questions, the loop skips the refinement round |
| `complete_json` in `refine` | any model error | `RetryableError` or `ToolError` | returns no patches, the itinerary keeps its version |
| model output | a patch that does not apply | `apply_patch` raises `ValueError` on a copy | that patch is dropped, the rest still return |
| model output | a `signal_id` that was never passed in | set membership | the id is stripped from the stop |
| model output | more than eight patches | length check | the extras are dropped and counted in `last_dropped` |

No bare `except`: each path catches `ToolError`, `RetryableError` or `ValidationError` by name.

## Tests that prove it

Offline. `trip_core.llm.complete_json` is replaced with a stub that returns a payload recorded in
`packages/itinerary/tests/recorded/`. No network, no key, no model call in any test.

| File and name | Plants | Asserts |
| --- | --- | --- |
| `tests/test_questions.py::test_caps_at_four` | a recorded payload of seven questions | four come back |
| `tests/test_questions.py::test_skips_answered_questions` | a brief whose answers already hold two of them | neither is asked again |
| `tests/test_refine.py::test_returns_patches_not_an_itinerary` | a recorded remove and add | both are `ItineraryPatch`, and the itinerary passed in is unchanged |
| `tests/test_refine.py::test_drops_a_patch_that_does_not_apply` | a remove naming a stop id that is not there | it is dropped, the other patch survives, nothing raises |
| `tests/test_refine.py::test_strips_invented_signal_ids` | an added stop citing `sig-99` | the stop comes back citing only real ids |
| `tests/test_refine.py::test_caps_the_patch_count` | a recorded payload of twelve patches | eight come back and the drop is counted in `last_dropped` |
| `tests/test_refine.py::test_model_failure_returns_no_patches` | a stub raising `RetryableError` | an empty list, no exception, the reason recorded |
| `tests/test_questions.py::test_model_failure_returns_no_questions` | a stub raising `ToolError` | an empty list, no exception, the loop skips the round |
| `tests/test_replace_failed.py::test_one_patch_per_failed_stop` | a report failing two of six stops | two patches, and the four passing stops are untouched |
| `tests/test_replace_failed.py::test_no_candidate_becomes_a_remove` | signals offering no unused place | the patch op is `remove` |
| `tests/test_replace_failed.py::test_never_reuses_a_skipped_place` | an answer reading `skip: Night Market` | no patch puts that place back |
| `tests/test_planner_end_to_end.py::test_fixture_runs_with_the_real_planner` | the tokyo fixture, every model call stubbed | the loop completes and the itinerary version is greater than 1 |

The reliability claims are the dropped patch and the model failure. Watch both go red first and say so.

## Out of scope

- `draft()`. It delegates to the fake in this PR and gets its own spec.
- `build_resolver()`, `build_verifier()` and `build_calendar()`. They keep raising `NotImplementedError`.
- Asking the traveller a follow-up to their answer. One round of questions, one round of patches.
- Prompt tuning past the point where the tests pass. That is reliability-hour work, not this PR.

## Done when

- `make check` green
- `make fixture` green, unchanged on fakes
- `REAL_PLANNER=1 uv run trip --brief evals/trips/lisbon.json` asks at most four questions and applies patches,
  with the itinerary version climbing by one per patch in the call log
- eval rows: no row is Lane C's alone here, but the loop row must stay green with the real planner on
- demo moment: at 0:55, the agent asks one question, the answer patches one stop, and only that stop moves
