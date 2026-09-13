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
