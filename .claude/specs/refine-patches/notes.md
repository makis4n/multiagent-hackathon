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

| 4 refine and the apply filter | 4d33e76 | pass with notes | red-first reproduced by the reviewer, both directions |

## Task 4 notes, carried forward

1. **For task 5.** `last_dropped.extend(mapped.dropped)` in `planner.py` is the one new line with no test behind it:
   replacing it with `pass` leaves the suite green, so mapping-layer drops go unrecorded as far as the tests know.
   A payload with an unknown op, asserted into `last_dropped`, closes it.
2. The drop-line index numbering differs between the two layers, so one round can produce two lines both reading
   `patch 1`. These lines are the operator's only view of what the model asked for, so make them distinguishable.
3. `test_refine.py` pins the day-range drop with a bare `"9" in line`, which would also match `patch 9:`. It does
   discriminate today and it does go red under mutation. Tighten it to the full phrase when next in that file.
4. Conformant by design, recorded so nobody "fixes" it: a patch depending on a stop an earlier patch created is
   rejected by the mapping, because Behaviour 5 requires a stop id that exists in the itinerary as passed in.
5. Once the cap is reached the remaining candidates are recorded as over-the-cap without being applied, so one that
   was also inapplicable is reported only as a cap drop. Cheaper, and harmless.

| 5 degrade on model failure | 5ae258d | pass with notes | four degrade tests reproduced red by the reviewer |

## Task 5 notes, carried forward

1. **Orchestrator's call: this one is a rule 12 breach, not a note, and task 6 fixes it.** `log.exception` writes the
   full traceback, whose last line is the exception message. On the validation path that message quotes the model's
   own output. Rule 12 reads "no raw request or response bodies. Log the stack, not the message." The drop line
   itself is clean; only the logger leaks. One line to fix.
2. **For task 7.** Nothing calls `logging.basicConfig`, so that traceback reaches the last-resort handler and prints
   to stderr. A degrade is supposed to look like no change, not like a crash mid-run. Task 7 decides the handler.
3. **For task 6.** The new `last_dropped` reset in `questions` is pinned by no test: deleting it leaves the suite
   green, so stale refine drops would read as questions drops.
4. **For task 6.** The "type name only, no message" property is unguarded. Rewriting the append to include the
   message leaves the suite green, and that property is the rule 8 claim in the commit message. Pin the exact line.
5. **For task 7.** `last_dropped` is read by nothing outside the tests. Behaviour 7 and 10 say drops are recorded;
   today they are recorded nowhere a human looks. Surface it through the call log or the CLI.

Confirmed clean by the reviewer: the catch is narrow, no `Exception` and no bare `except`, the prompt builders sit
outside the try so a programming error still escapes, and an empty return from either method lets the loop fall
through to resolve, verify and book with the itinerary unchanged.

| 6 replace_failed and the rule 12 fix | 17f3a97 | pass with notes | log leak fixed red-first, eleven mutations reproduced |

## Task 6 notes, carried forward

1. **Reviewer method, worth keeping.** Its first mutation run was worthless: the copied virtualenv resolved the
   editable install back to the real repo, so mutations appeared to survive. It caught that itself and reran with
   the import path forced at the copy, verified by printing the module file. Any future mutation testing does the same.
2. **For task 7.** Behaviour 8's remove half is proven only through the reused-place route. No payload has the model
   stay silent about a failed stop, which is the other way a remove happens.
3. **For task 7.** Two failed stops cannot be given the same replacement place. The code enforces it, no test holds it.
4. **For task 7, a decision not a chore.** `last_dropped` no longer carries exception messages, but it does carry
   model output fragments: a proposed place name, an unknown op string, a bad time string. Today nothing reads it,
   so no rule is broken. Piping it into `CallLog` would turn those into log lines and put rule 12 back in play.
5. **For task 7.** Every entry point rebinds `last_dropped`, so one loop round keeps only the last call's drops.
   A reader must read it immediately after each call.
6. The two `skip:` implementations agree, and the planner's is the looser one, so nothing the fake skips comes back.
   They part company only on non-ASCII case folding. Recorded, not worth changing.
7. A stop failing two checks is deduped by the report itself, so one patch per failed stop holds. No test plants
   that shape, and a real verifier will produce it.
