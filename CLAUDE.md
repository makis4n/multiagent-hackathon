# multiagent-hackathon

The trip agent for the Multi-App AI Agent Hackathon, Sunday 13 Sep 2026. `PLAN.md` is the run sheet,
`ARCHITECTURE.md` is the loop. This file binds every human and every AI coding agent (Claude Code, Cursor, Codex)
working in this repo.

## Layout and ownership

```
packages/core/        trip_core       THE CONTRACT: models, Protocols, fakes, llm, the tokyo fixture   Lane A
packages/research/    trip_research   Reddit, YouTube, web search -> Signal[]                          Lane B
packages/itinerary/   trip_itinerary  draft, refine, resolve, verify, calendar                         Lane C
packages/booking/     trip_booking    Duffel flights and stays, activities, the confirmation gate      Lane D
apps/agent/           trip_agent      the loop, registry, CLI, Streamlit page, call log                Lane A
evals/                                ten briefs, the eval runner, results per SHA                     Lane A
```

One owner per package. Claim a package by putting your name on the status line of its `README.md` in your first
commit. Touching another lane's package: say so in the team chat first; the owner answers with what is yours.

## Run

```sh
uv sync --all-packages                    # once; uv installs Python itself
make check                                # ruff, basedpyright, pytest: this is CI
make fixture                              # uv run trip --fixture tokyo --auto-confirm: end to end on fakes
uv run trip --brief evals/trips/lisbon.json
make ui                                   # Streamlit on http://localhost:8501
make evals                                # every brief in evals/trips -> evals/results/<sha>.md
```

Copy `.env.example` to `.env`. `REAL_RESEARCH=1`, `REAL_PLACES=1`, `REAL_PLANNER=1`, `REAL_VERIFIER=1`,
`REAL_BOOKING=1`, `REAL_CALENDAR=1` each select a lane's real implementation; unset means the fake.

## Rules

1. **The contract only grows.** `packages/core` changes additively only. Announce every change in the team chat as
   `<lane>: CONTRACT — <what>`. Renames and removals need Lane A's OK. A new Protocol member ships with every
   implementer and every fake updated in the same PR. `make check` is the proof.
2. **One owner per package.** See above.
3. **Branch `lane/<letter>-<topic>` off main. Commit every logical step.** `git pull --rebase origin main` before
   every push. `--force-with-lease` only on your own branch. Never amend a pushed commit. Never force-push main.
4. **Small PRs, opened non-draft the moment `make check` passes.** Merge main into your branch before opening. CI
   green on your head SHA. One GitHub issue per PR; the PR closes it. Anyone but the author may merge on green.
   Lane A breaks ties.
5. **Every tool is a plain function or class** over contract types, callable without a model. Every Protocol has
   a fake. Tests run offline against recorded responses (`respx`). No network in CI. A tool without a fake and a
   recorded test is not done.
6. **Reliability claims are proven by a test, not prose.** Retry, idempotency, the confirmation gate and the
   budget cap each have a test that plants the failure and watches it go red against the old code.
7. **Money rule.** No order without `confirmed_by_user_at`. Every order carries an idempotency key that the
   provider looks up before creating anything, so a retry never creates a second order. Sandbox keys only, all
   day; the Duffel client refuses a key that does not start with `duffel_test_`.
8. **Secrets live in `.env` only.** `.env.example` declares each key with an empty value, grouped by lane. Never a
   key in chat, code, a scratch file or a log line.
9. **Verified facts, not memory.** Pin package versions through `uv.lock`. Read the installed library's docs before
   building on it (google-genai, streamlit, duffel). Empty output is unknown, not verified.
10. **Nothing merges that breaks `make fixture`.** There is always a main that runs end to end.
11. **AI coding agents** follow this file, run `make check` before every push, and never edit `packages/core`
    without a human message in the team chat first.
12. **Logs.** One JSONL line per tool call through `CallLog`. No raw request or response bodies. Log the stack,
    not the message. Every third-party response checks its status. No bare `except`.
13. **Copy.** Controls say what happens. No em dashes in anything the user or the judges see.

## Code

- Model calls go through `trip_core.llm.complete_json` with a flat pydantic response schema: str, int, float,
  bool, lists, nested models, `X | None`. No dicts.
- The loop is code; the model fills typed slots. Do not add a free-running tool-calling agent.
- Patches are the only way an itinerary changes after the draft. `apply_patch` is pure.
- Comments stay under a tenth of the lines in a file; a comment states a constraint the code cannot show.
- Verify before handing off: run what you built and show the evidence.

## Contract change procedure

1. Say it in the team chat before you start.
2. Add; never rename or remove.
3. Update every fake and every implementer in the same PR.
4. `make check` green.
5. When merged, post `<lane>: CONTRACT — <what changed, what to pull>`.

## Chat templates

```
Claiming a lane: <lane> (<letter>, <name>). <scope in one line>. Contract: <additive changes or none>.
Touches: <packages/files>. Branch <name>, PR to follow.

<lane>: CONTRACT — <what changed, what to pull>
<lane>: LIVE — <what works on main, the command to try it>
<lane>: BLOCKED — <what, who can unblock, what you are doing meanwhile>
<lane>: QUESTION — <one decision, the options, the default if nobody answers in 10 min>
```
