# multiagent-hackathon

A trip agent for the Multi-App AI Agent Hackathon, 13 Sep 2026. Give it a destination, dates, party size, a
budget band and a few style words. It reads what people posted recently (YouTube, Reddit through web search),
drafts a day-by-day itinerary with Claude in which every stop cites its source, asks up to four questions and
turns the answers into edits, verifies every stop against Google Places and Routes (exists, open at that hour,
reachable from the previous stop), swaps or drops what fails and says why, then books the flight in Duffel's
sandbox only after a click. A retry never books twice.

- `BRIEF.md`: the system and reliability brief. What is real, every failure mode with its test, the eval table.
- `DEMO.md`: the two-minute demo, beat by beat.
- `ARCHITECTURE.md`: the loop. `CLAUDE.md`: the rules that bound everyone working here. `PLAN.md`: the run sheet.

## Status at submission

| part | state |
| --- | --- |
| Research | live: YouTube Data API, Exa scoped to reddit.com. Reddit's own API is written, unwired (policy). |
| Planner | live: Claude Sonnet 5 drafts and replaces, Haiku 4.5 asks and extracts. Gemini behind `LLM_PROVIDER=gemini`. |
| Places and Routes | live: Google Places API (New), Google Routes API. Transit falls back to a labelled driving estimate. |
| Booking | live: Duffel test mode, flights. Idempotent orders with lost-response recovery. Stays and activities: fakes. |
| Calendar | fake. Cut for the day. |
| Tests | `make check`: ruff, basedpyright, 139 tests, offline. CI runs the same. |
| Evals | ten briefs, seven checks each, `evals/results/<sha>.md`. The submission table is in `BRIEF.md`. |

## Run

```sh
uv sync --all-packages
cp .env.example .env                      # fill in the keys for the lanes you run for real
make fixture                              # the seed trip, end to end on fakes
make check                                # ruff, basedpyright, pytest: CI runs exactly this
make ui                                   # Streamlit on http://localhost:8501
make evals                                # evals/results/<sha>.md
```

`uv run trip --help` for the CLI. `REAL_<LANE>=1` in `.env` swaps a fake for the lane's real implementation:
`RESEARCH`, `PLACES`, `PLANNER`, `VERIFIER`, `BOOKING`, `CALENDAR`. `INJECT_BOOKING_FAILURE=1` makes the first
order call lose its response after the provider has created the order, so you can watch the retry find it.

Keys for a full real run: `ANTHROPIC_API_KEY`, `YOUTUBE_API_KEY`, `EXA_API_KEY`, `GOOGLE_MAPS_API_KEY` (Places
API New and Routes API enabled), `DUFFEL_API_KEY` (a `duffel_test_` key; anything else is refused).

## Layout

```
packages/core/        trip_core       the contract: models, Protocols, fakes, the model wrapper, the tokyo fixture
packages/research/    trip_research   Lane B: YouTube, web search -> Signal[]
packages/itinerary/   trip_itinerary  Lane C: draft, refine, resolve, verify
packages/booking/     trip_booking    Lane D: Duffel flights, the confirmation gate, idempotent orders
apps/agent/           trip_agent      Lane A: the loop, registry, CLI, Streamlit page, call log
evals/                                ten briefs, the eval runner, results per SHA
```

## Lanes

| lane | owner | package | factory |
| --- | --- | --- | --- |
| A base and orchestrator | Wai Kin | `packages/core`, `apps/agent`, `evals` | |
| B research | Reiner Ong | `packages/research` | `build_sources()` |
| C itinerary and verification | Wai Kin (C1, C2); C3 #14 open; C4 cut | `packages/itinerary` | `build_resolver()`, `build_planner()`, `build_verifier(resolver)` |
| D booking | Kieron Oei (D1), Wai Kin (D2, D4); D3 cut | `packages/booking` | `build_provider()` |

## The contract

Everything crosses package boundaries as `trip_core.models` types through the Protocols in `trip_core.tools`.
Each Protocol has a fake in `trip_core.fakes`, and `make fixture` runs the whole loop on them. The contract
changes additively only; every change is announced in the team chat as `<lane>: CONTRACT — <what>`.

## CI

`.github/workflows/ci.yml` runs `make check` on every push and every PR. Merge only on a green run for your head
SHA.
