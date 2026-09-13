# multiagent-hackathon

A trip agent for the Multi-App AI Agent Hackathon, 13 Sep 2026. Given a destination, dates and a short
questionnaire it researches what is good right now (Reddit, YouTube), drafts a day-by-day itinerary, refines it
through a few questions, verifies every stop against Google Places and Routes, books flights and stays in Duffel
test mode behind a human confirmation gate, and writes the trip to Google Calendar.

Read `CLAUDE.md` (binds everyone working here), `ARCHITECTURE.md` (the loop) and `PLAN.md` (the run sheet).

## Layout

```
packages/core/        trip_core       the contract: models, Protocols, fakes, the Gemini wrapper, the tokyo fixture
packages/research/    trip_research   Lane B: Reddit, YouTube, web search -> Signal[]
packages/itinerary/   trip_itinerary  Lane C: draft, refine, resolve, verify, calendar
packages/booking/     trip_booking    Lane D: Duffel flights and stays, activities, the confirmation gate
apps/agent/           trip_agent      Lane A: the loop, registry, CLI, Streamlit page, call log
evals/                                ten briefs, the eval runner, results per SHA
```

## Run

```sh
uv sync --all-packages
cp .env.example .env                      # fill in the keys for the lanes you run for real
make fixture                              # the seed trip, end to end on fakes
make check                                # ruff, basedpyright, pytest: CI runs exactly this
make ui                                   # Streamlit
make evals                                # evals/results/<sha>.md
```

`uv run trip --help` for the CLI. `REAL_<LANE>=1` in `.env` swaps a fake for the lane's real implementation:
`RESEARCH`, `PLACES`, `PLANNER`, `VERIFIER`, `BOOKING`, `CALENDAR`.

## Lanes

| lane | owner | package | factory to implement |
| --- | --- | --- | --- |
| A base and orchestrator | Wai Kin | `packages/core`, `apps/agent`, `evals` | |
| B research | unclaimed | `packages/research` | `build_sources()` |
| C itinerary and verification | unclaimed | `packages/itinerary` | `build_resolver()`, `build_planner()`, `build_verifier(resolver)`, `build_calendar()` |
| D booking | unclaimed | `packages/booking` | `build_provider()` |

Claim a package by putting your name on the status line of its `README.md` in your first commit, then post
`Claiming a lane: ...` in the team chat (template in `CLAUDE.md`).

## The contract

Everything crosses package boundaries as `trip_core.models` types through the Protocols in `trip_core.tools`.
Each Protocol has a fake in `trip_core.fakes`, and `make fixture` runs the whole loop on them. After milestone 1
the contract changes additively only; every change is announced in the team chat as `<lane>: CONTRACT — <what>`.

## CI

`.github/workflows/ci.yml` runs `make check` on every push and every PR. Merge only on a green run for your head
SHA. A PR with conflicts gets no PR run at all, which is why the push trigger exists: merge main into your branch
before opening the PR.
