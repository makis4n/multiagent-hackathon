# Shared reference for the spec skills

Read with `CLAUDE.md`. This file is the lookup table the spec skills use; `CLAUDE.md` is the authority
and wins on every conflict.

## Lanes and ownership

| Lane | Owner | Packages | Factories to implement |
| --- | --- | --- | --- |
| A base and orchestrator | Wai Kin | `packages/core`, `apps/agent`, `evals`, CI, docs | the loop, registry, CLI, UI, call log |
| B research | see package README | `packages/research` | `build_sources()` |
| C itinerary and verification | see package README | `packages/itinerary` | `build_resolver()`, `build_planner()`, `build_verifier(resolver)`, `build_calendar()` |
| D booking | see package README | `packages/booking` | `build_provider()` |

The status line of each package `README.md` names the live owner. Trust that line over this table.

Branch names: `lane/<letter>-<topic>`, for example `lane/c-verifier-transit`.

## The Protocols a feature can implement

`packages/core/trip_core/tools.py`:

- `ResearchSource.search(brief) -> list[Signal]` (Lane B)
- `PlaceResolver.resolve(name, near)`, `.get(place_id)` (Lane C)
- `ItineraryPlanner.draft`, `.questions`, `.refine`, `.replace_failed` (Lane C)
- `Verifier.verify(itinerary) -> VerificationReport` (Lane C)
- `BookingProvider.search(brief, kind)`, `.order(option, idempotency_key, confirmed_by_user_at)` (Lane D)
- `CalendarSink.export(itinerary, brief) -> str` (Lane C)
- `resolve_places(itinerary, resolver, near)` is pure and lives in core

Each Protocol has a deterministic fake in `trip_core.fakes`. A real implementation is selected by its flag:
`REAL_RESEARCH`, `REAL_PLACES`, `REAL_PLANNER`, `REAL_VERIFIER`, `REAL_BOOKING`, `REAL_CALENDAR`.

## Commands

```sh
uv sync --all-packages
make check                       # ruff, basedpyright, pytest. This is CI.
make fixture                     # uv run trip --fixture tokyo --auto-confirm
make evals                       # every brief in evals/trips -> evals/results/<sha>.md
uv run pytest packages/<pkg>     # one package
make format                      # ruff format, ruff check --fix
```

## The rule checklist a feature is judged against

Numbers are the `CLAUDE.md` rules.

1. Contract additive only. A new Protocol member ships with every fake and every implementer in the same PR.
   Renames and removals need Lane A. Announce in the team chat before touching `packages/core`.
2. One owner per package. Another lane's package needs a message in the team chat first.
3. Branch off main, commit every logical step, `git pull --rebase origin main` before every push.
4. Small PR, non draft the moment `make check` passes, one issue per PR.
5. Every tool is a plain function or class over contract types, callable without a model. Every Protocol has a
   fake. Tests run offline against recorded responses with `respx`. No network in CI.
6. Reliability claims are proven by a test that plants the failure, not by prose.
7. No order without `confirmed_by_user_at`. Every order carries an idempotency key the provider looks up first.
   Duffel keys must start with `duffel_test_`.
8. Secrets live in `.env` only. `.env.example` declares each key with an empty value.
9. Verified facts, not memory. Read the installed library docs. Empty output is unknown, not verified.
10. Nothing merges that breaks `make fixture`.
12. One JSONL line per tool call through `CallLog`. No raw bodies. Log the stack, not the message. No bare `except`.
13. Copy: controls say what happens, and no em dashes in anything a user or a judge sees.

Model calls go through `trip_core.llm.complete_json(prompt, Schema)` with a flat pydantic schema: str, int, float,
bool, lists, nested models, `X | None`. No dicts. The loop is code; the model fills typed slots. Patches are the
only way an itinerary changes after the draft.

## Eval rows a feature may have to move

| Check | Pass condition | Lane |
| --- | --- | --- |
| signals | at least 15 signals, at least 10 distinct places, every URL returns 200 | B |
| resolved | every stop resolves to a place_id | C |
| verified | at least 90 percent of stops pass exists, open, reachable, in_window | C |
| transit | 45 min or less between consecutive stops | C |
| bookable | at least one flight option and one stay option | D |
| gated | zero orders without `confirmed_by_user_at`; an injected 500 yields exactly one order | D |
| loop | the full run completes with no unhandled exception, call log complete | A |

## Chat templates

```
Claiming a lane: <lane> (<letter>, <name>). <scope in one line>. Contract: <additive changes or none>.
Touches: <packages/files>. Branch <name>, PR to follow.

<lane>: CONTRACT — <what changed, what to pull>
<lane>: LIVE — <what works on main, the command to try it>
<lane>: BLOCKED — <what, who can unblock, what you are doing meanwhile>
<lane>: QUESTION — <one decision, the options, the default if nobody answers in 10 min>
```

## Spec layout

One directory per feature under `.claude/specs/<slug>/`:

- `spec.md` the contract of the change: goal, lane, behaviour, tests that prove it, done conditions
- `tasks.md` the ordered checklist `build-spec` works through
- `notes.md` optional, written by `check-spec` and `ship-spec` with findings and links

Specs are working files, not deliverables. Commit them only if the team wants them reviewed.
