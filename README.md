# Tripia

Give it a destination, dates, party size, a budget band and a few style words. Tripia researches what people
posted about the place recently, drafts a day-by-day itinerary where every stop cites the post it came from,
asks up to four questions and turns your answers into edits, checks every stop against Google (does it exist,
is it open at that hour, can you get there in time from the last stop), swaps or drops whatever fails and says
why, then books the flight in Duffel's sandbox, never before you click confirm.

## The loop

```
brief → research → draft → questions → patches → resolve → verify → replace failures → book → calendar
```

The loop is plain code; the model only fills typed slots inside it (a draft, an answer to a patch, a place
name). Nothing free-running, nothing that decides which tool to call next on its own. See `ARCHITECTURE.md` for
the full shape and `trip_core.tools` for the Protocol each stage implements.

## Run it

```sh
uv sync --all-packages
cp .env.example .env              # fill in keys for whichever parts you want live; see below
make fixture                      # the seed trip end to end, no keys needed
make check                        # ruff, basedpyright, pytest — same as CI
make ui                           # Streamlit at http://localhost:8501
```

`make fixture` runs the whole loop on deterministic fakes with zero keys and zero network calls, which is the
fastest way to see the shape of the thing. `uv run trip --help` shows the CLI; `uv run trip --brief
evals/trips/lisbon.json` runs a specific brief instead of the seed one.

Every stage of the loop has a real implementation and a fake behind the same interface. `REAL_<STAGE>=1` in
`.env` switches one stage from its fake to the real thing; leave it unset and you get the fake. Mix and match
freely, the loop doesn't care which stages are real.

```
REAL_RESEARCH=1     # YouTube + Exa, needs YOUTUBE_API_KEY and EXA_API_KEY
REAL_PLANNER=1       # Claude Sonnet 5 / Haiku 4.5, needs ANTHROPIC_API_KEY
REAL_PLACES=1        # Google Places API (New), needs GOOGLE_MAPS_API_KEY
REAL_VERIFIER=1      # Google Routes API, same key
REAL_BOOKING=1       # Duffel test mode, needs a duffel_test_ key; a live key is refused
```

`.env.example` lists every key with an empty value, grouped by which part of the loop uses it. `LLM_PROVIDER`
switches the model wrapper between `anthropic` (default) and `gemini`, same typed interface either way.

## What's real and what's a stand-in

| stage | real implementation | fake behind the same interface when unset |
| --- | --- | --- |
| research | YouTube Data API v3 search, Exa general web search, both feeding a heuristic-plus-model place extractor | 16 deterministic signals per destination |
| planner | Claude drafts, asks up to four questions, turns answers into patches (rule based today, not model based) | patches from the fixture's signals, one deliberately closed venue so the verifier has something to catch |
| places | Google Places API (New): text search, opening hours | coordinates hashed from the place name, so distances are stable but not real |
| verifier | exists, open at the planned hour, reachable within 45 minutes (Google Routes, falling back to a labelled driving estimate when Routes has no transit for a route), inside the trip window | the same four checks against the fake places |
| booking | Duffel test mode, flights only. Idempotent: a retry after a lost response never creates a second order | flights and stays, no purchase ever crosses a real gate |
| calendar | not built; this stage always uses the fake | returns a fake URL |

Reddit's own API is written and tested (`packages/research/trip_research/reddit.py`) but not wired into
`build_sources()`: their Responsible Builder Policy needs approval nobody here has yet. Nothing is ordered
without an explicit click; every order carries an idempotency key the provider checks before creating anything.

## Layout

```
packages/core/        trip_core       the contract: models, Protocols, fakes, the model wrapper, the seed fixture
packages/research/    trip_research   YouTube + web search to Signal[]
packages/itinerary/   trip_itinerary  draft, questions, refine, resolve, verify
packages/booking/     trip_booking    Duffel flights, the confirmation gate, idempotent orders
apps/agent/           trip_agent      the loop, the registry that wires real/fake per stage, the CLI, the Streamlit page
evals/                                ten destination briefs, the eval runner, one results table per commit
```

Every package owns one side of `trip_core.tools`' Protocols and ships a fake for it alongside the real thing, so
`make fixture` always runs end to end even when a whole lane is unbuilt. The contract in `packages/core` changes
additively only, one Protocol member shipping with every implementer and fake in the same change.

## Further reading

- `ARCHITECTURE.md` — the loop stage by stage, the money and safety rules, the model wrapper
- `BRIEF.md` — the reliability brief: every failure mode with the test that proves it, the eval table
- `DEMO.md` — the two-minute walkthrough script
- `CLAUDE.md` — the rules bounding everyone and every coding agent working in this repo
- `PLAN.md` — the original run sheet this was built against

## Tests and evals

```sh
make check     # ruff, basedpyright, pytest, offline; CI runs exactly this
make evals     # runs all ten briefs in evals/trips, writes evals/results/<sha>.md
```

Every test runs offline against recorded responses (respx for HTTP, a monkeypatched model call for the
LLM-backed pieces); nothing in `make check` touches the network. `evals/results/` holds one table per commit
that was measured against real tools, so results are always tied to a specific SHA.
