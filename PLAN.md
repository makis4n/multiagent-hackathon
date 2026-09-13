# Trip Agent Run Sheet

Multi-App AI Agent Hackathon, Sunday 13 Sep 2026, virtual, Pacific Time. Team of 4: Wai Kin, keaenlim, Reiner-Ong, KieronOei.
Repo: https://github.com/makis4n/multiagent-hackathon

**Submission by 16:00 PT (01:00 CEST):** working repo, two-minute demo, system and reliability brief.
Judging weights: technical execution 30, reliability and evaluation 25, usefulness 20, originality 15, demo clarity 10.

**The product in one line:** given a destination, dates and a short questionnaire, the agent researches what is
actually good right now (Reddit, YouTube), drafts a day-by-day itinerary, refines it through a few questions,
verifies every stop against Google Places and Routes, and books flights and stays in Duffel test mode behind a
human confirmation gate, then writes the trip to Google Calendar.

**How this plan works** (copied from Daniel's hackathon at Depict, Sep 1-3): one person pushes a small base to
`main` first, the *contract* everyone builds against. Then four lanes build in parallel against that contract, each
owning one package, and the contract only ever grows. Every PR passes one `make check`. Nothing merges that breaks the
fixture run. The base owner coordinates and merges.

---

## 1. Timeline

Times are PT with CEST in brackets. SGT is CEST plus 6.

| PT | CEST | What | Who |
|---|---|---|---|
| 11:00 | 20:00 | Decide model provider and stack (below). Lane A starts milestone 1. Lanes B, C, D sign up for keys and spike their API. | all |
| 11:30 | 20:30 | `base: MILESTONE1 — <repo> @ <sha>`. `uv run trip --fixture tokyo` runs end to end on fakes. Everyone branches. | A |
| 11:30-12:45 | 20:30-21:45 | Build 1: first real tool per lane replaces its fake behind a flag. Recorded test per tool. | B, C, D |
| 12:45 | 21:45 | Catch-up 1 (10 min, one thread): main runs the fixture with real research and a real draft, fake booking. | all |
| 12:45-14:00 | 21:45-23:00 | Build 2: verifiers, refinement questions, Duffel order plus gate, calendar export. | B, C, D |
| 14:00 | 23:00 | Catch-up 2: full flow on main. Eval runner starts producing the results table. | all |
| 14:00-15:00 | 23:00-00:00 | Reliability hour: run the 10 eval trips, fix the top failures, prove retry and idempotency by test, fill the brief. | all |
| 15:00 | 00:00 | Code freeze. Fixes only. | A calls it |
| 15:00-15:40 | 00:00-00:40 | Demo script, record the two minutes, README, brief final. | A records, others review |
| 15:40-16:00 | 00:40-01:00 | Submit. Buffer. | A |
| 16:00 | 01:00 | Judging. | |

**If behind at 14:00, cut in this order:** activity deep links, then YouTube, then stays, then calendar export.
**Never cut:** the verifiers, the confirmation gate, the eval results table, the recorded demo.

---

## 2. The base (milestone 1, pushed to main by 11:30)

Lane A pushes this alone. Nobody else touches `main` until the announcement. Everything below already runs with fakes.

```
multiagent-hackathon/
  pyproject.toml              uv workspace root
  Makefile                    check = ruff check, ruff format --check, pyright, pytest
  .env.example                every key, empty values, grouped by lane
  .github/workflows/ci.yml    make check on every push and PR
  CLAUDE.md                   = AGENTS.md. Binds every human and AI coding agent. Section 4 of this plan.
  ARCHITECTURE.md             one page: the loop, the contract, what is sandbox
  README.md                   layout, run, lanes table, how to claim a package
  packages/core/              trip_core. THE CONTRACT. Owner: A
    models.py                 pydantic models below
    tools.py                  Protocols below
    fakes.py                  a deterministic offline fake for every Protocol
    llm.py                    complete_json(prompt, Schema) over Gemini
    fixtures/tokyo.json       the seed trip: Tokyo, 5 days, food and art, 2 travellers, plus 18 signals
  packages/research/          Owner: B. Reddit, YouTube, web search -> Signal[]
  packages/itinerary/         Owner: C. draft, patch, verify, calendar
  packages/booking/           Owner: D. Duffel flights and stays, activity search, confirm gate
  apps/agent/                 Owner: A
    loop.py                   brief -> research -> draft -> refine -> verify -> book. One function per stage.
    registry.py               which implementation backs each Protocol. Env flag per tool: REAL_RESEARCH=1 ...
    cli.py                    uv run trip --fixture tokyo
    ui.py                     Streamlit: chat left, itinerary right, confirm modal. Only A edits it.
    log.py                    every tool call -> logs/calls.jsonl (trip_id, tool, input_hash, ms, ok, error)
  evals/
    trips/*.json              10 briefs
    run.py                    runs each brief through the loop, writes evals/results/<sha>.md
```

### The contract: models (`packages/core/models.py`)

| Model | Fields | Produced by | Consumed by |
|---|---|---|---|
| `TripBrief` | id, destination, origin, start_date, end_date, travellers, budget_band, styles[], answers{} | UI | everyone |
| `Signal` | id, source (reddit, youtube, web), url, title, excerpt, places_mentioned[], posted_at, score | B | C |
| `Place` | id (Google place_id), name, address, lat, lng, opening_hours{weekday: ranges}, rating, price_level | C | C, A |
| `Stop` | id, day, start, end, place_name, place_id (None until resolved), category, why, signal_ids[], status (draft, verified, failed), failure_reason | C | A, D |
| `Day` / `Itinerary` | date, stops[] / id, brief_id, version, days[], notes | C | A, D |
| `ItineraryPatch` | op (add, remove, move, replace), stop, target_day, position | C | C |
| `VerificationReport` | itinerary_id, checks[] {stop_id, check (exists, open, reachable, in_window), ok, detail}, passed | C | A |
| `BookingOption` | kind (flight, stay, activity), provider, provider_ref, title, price_minor, currency, details{} | D | A |
| `BookingOrder` | id, option, idempotency_key, confirmed_by_user_at, status (pending, confirmed, failed), provider_order_id, receipt | D | A |

### The contract: Protocols (`packages/core/tools.py`)

- `ResearchSource.search(brief) -> list[Signal]`
- `PlaceResolver.resolve(name, near) -> Place | None` and `get(place_id) -> Place | None`
- `ItineraryPlanner.draft(brief, signals) -> Itinerary`, `questions(brief, itinerary) -> list[str]`, `refine(brief, itinerary, answers, signals) -> list[ItineraryPatch]`, `replace_failed(brief, itinerary, report, signals) -> list[ItineraryPatch]`
- `Verifier.verify(itinerary) -> VerificationReport`
- `BookingProvider.search(brief, kind) -> list[BookingOption]` and `order(option, idempotency_key, confirmed_by_user_at) -> BookingOrder`
- `CalendarSink.export(itinerary, brief) -> str` (URL)
- `resolve_places(itinerary, resolver, near)` in `trip_core.tools` sets `place_id` on every stop; the loop calls it before `verify`

Every Protocol has a fake in `fakes.py`. The fixture trip runs through all of them on fakes (`make fixture`) before
anyone writes a real one. That is what "milestone 1 is done" means. The tree above is what is on `main`.

**While A builds the base (11:00-11:30), B, C and D:** create their API keys, run a 20-line spike that hits their
API once and saves the raw response as a test cassette, and read the Protocol they implement.

---

## 3. Lanes

One owner per package. Claim it by writing your name in the package README status line in your first commit.

### Lane A: base and orchestrator (Wai Kin)

Owns `packages/core`, `apps/agent`, `evals`, CI, docs, the merges, the catch-ups, the brief, the demo.

| By (PT) | Deliverable |
|---|---|
| 11:30 | Milestone 1 pushed. Fixture runs on fakes. Announcement posted. |
| 12:45 | Registry flags wire real tools as they land. Streamlit page shows brief, itinerary, confirm modal. |
| 14:00 | Eval runner and call logging. First results table committed. |
| 15:40 | Brief, README, demo recorded. |

Demo moment: the whole loop in one run.

### Lane B: research

Keys: Reddit script app (client id and secret), YouTube Data API v3, Exa or Tavily.

| By (PT) | Deliverable |
|---|---|
| 12:15 | Reddit search over destination subreddits and r/travel -> `Signal[]`, with a recorded test. |
| 12:45 | YouTube search plus transcripts of recent vlogs -> `Signal[]`. |
| 13:45 | Ranking and dedupe (Haiku), place-name extraction, recency weighting so "trendy" is measurable (posted in the last 90 days scores higher). |
| 14:30 | Eval rows pass: per trip at least 15 signals, at least 10 distinct places, every URL returns 200. |

Demo moment: a stop labelled with its source, for example a subreddit thread from three weeks ago.

### Lane C: itinerary and verification

Keys: Google Places API (New), Routes API, one Google Calendar OAuth desktop credential.

| By (PT) | Deliverable |
|---|---|
| 12:15 | Draft: brief plus signals -> `Itinerary` via structured output. Every stop names a place and cites signal ids. |
| 13:00 | `PlaceResolver` and `Verifier`: exists, open at the planned time on that weekday, reachable (45 min or less by transit between consecutive stops), inside the trip window. Failed stops get one replacement pass. |
| 13:45 | Refinement: the model asks at most 4 questions from gaps in the brief. Answers become `ItineraryPatch` ops applied to the JSON. Never a regeneration. |
| 14:30 | Calendar export. |

Demo moment: a closed or non-existent venue caught by the verifier and swapped on screen.

### Lane D: booking

Keys: Duffel test token (`duffel_test_` prefix), Viator affiliate or Amadeus self-service test.

| By (PT) | Deliverable |
|---|---|
| 12:15 | Duffel flight search -> `BookingOption[]`, with a recorded test. |
| 13:00 | Stays search. `order()` with an idempotency key and the `confirmed_by_user_at` gate. Client asserts the test-key prefix and refuses anything else. |
| 13:45 | Activity search plus deep link. Budget guard: sum of orders must stay within the brief's budget band or the order is refused. |
| 14:30 | Failure injection test: provider returns 500 once, retry, exactly one order exists under the same key. |

Demo moment: a confirmation number on screen, then the retry that recovers from an injected failure.

---

## 4. Rules (this section is CLAUDE.md)

1. **The contract only grows.** After milestone 1, `packages/core` changes additively only. Announce every change in
   chat as `<lane>: CONTRACT — <what>`. Renames and removals need Lane A's OK. A new Protocol member ships with every
   implementer and every fake updated in the same PR. `make check` is the proof.
2. **One owner per package.** Touching another lane's package: say so in chat first. The owner replies with what is
   yours ("new files under X are yours, stay out of Y").
3. **Branch `lane/<letter>-<topic>` off main. Commit every logical step.** `git pull --rebase origin main` before
   every push. `--force-with-lease` only on your own branch. Never amend a pushed commit. Never force-push main.
4. **Small PRs, opened non-draft the moment `make check` passes.** Merge main into your branch before opening. CI
   green on your head SHA. One GitHub issue per PR, the PR closes it. Anyone but the author may merge on green.
   Lane A breaks ties.
5. **Every tool is a plain function** with a pydantic input and output, callable without a model. Every Protocol has
   a fake. Tests run offline against recorded responses (respx). No network in CI. A tool without a fake and a
   recorded test is not done.
6. **Reliability claims are proven by a test, not prose.** Retry, idempotency, the confirmation gate and the budget
   cap each have a test that plants the failure and watches it go red against the old code.
7. **Money rule.** No order without `confirmed_by_user_at`. Every order carries an idempotency key stored before the
   provider call and looked up before any retry, so a retry never creates a second order. Sandbox keys only, all day.
8. **Secrets live in `.env` only.** `.env.example` declares each key with an empty value, grouped by lane. Never a key
   in chat, code, a scratch file or a log line.
9. **Verified facts, not memory.** Pin package versions from the registry. Confirm each API behaviour in its docs
   before building on it. Empty output is unknown, not verified.
10. **Nothing merges that breaks `uv run trip --fixture tokyo`.** From 12:45 there is always a main that runs end
    to end.
11. **AI coding agents** (Claude Code, Cursor, Codex) follow this file, run `make check` before every push, and never
    edit `packages/core` without a human message in chat first.
12. **Logs.** One JSONL line per tool call with a stable label. No raw request or response bodies. Log `error.stack`,
    not the message. Every third-party response checks `ok`. No bare `except`.
13. **Copy.** Controls say what happens. No em dashes in anything the user or the judges see.

---

## 5. Coordination

One group chat. Catch-ups happen in a thread so the channel stays readable. Message templates:

```
Claiming a lane: <lane> (<letter>, <name>). <scope in one line>. Contract: <additive changes or none>.
Touches: <packages/files>. Branch <name>, PR to follow.

<lane>: CONTRACT — <what changed, what to pull>
<lane>: LIVE — <what works on main, the command to try it>
<lane>: BLOCKED — <what, who can unblock, what you are doing meanwhile>
<lane>: QUESTION — <one decision, the options, the default if nobody answers in 10 min>
```

Catch-up format (12:45 and 14:00), three lines per lane: done, next, blocked. Never stall silently.

---

## 6. Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.13 (3.12 works), uv workspace, pydantic v2 | one toolchain, every API here has a Python SDK, evals are pytest |
| Quality gate | ruff, pyright (basic), pytest, respx for recorded HTTP | `make check` is CI |
| Model | google-genai SDK: Gemini Flash Lite for everything today (the bigger Flash models are overloaded or out of quota on the free tier), both through `trip_core.llm.complete_json` | one wrapper, flat JSON schemas, model names overridable in `.env` |
| Loop | hand-rolled, about 80 lines, one function per stage | no framework unknowns in a five-hour build |
| Research | PRAW, YouTube Data API v3 plus youtube-transcript-api, Exa or Tavily scoped to reddit.com | TikTok has no usable API; skip it |
| Places | Google Places API (New) text search and place details with `regularOpeningHours`; Routes API `computeRoutes` transit | deterministic verification |
| Booking | Duffel test mode (flights and stays); Viator affiliate or Amadeus Tours and Activities for activity search and deep links | real search results, sandbox orders with confirmation numbers |
| Calendar | Google Calendar API v3, one OAuth desktop credential | 30 lines, demos well, counts as an app |
| UI | Streamlit, one file, owned by A | zero frontend build; chat left, itinerary right, confirm modal |
| Evals | pytest runner over `evals/trips`, results table committed per SHA | feeds the brief directly |
| CI | GitHub Actions running `make check` | |

External apps: Reddit, YouTube, Google Places and Routes, Duffel, Viator or Amadeus, Google Calendar. Six, against
a minimum of three.

Decided at 11:00 PT: Python and Gemini. Neither changes today.

---

## 7. Evals and definition of done

Ten briefs in `evals/trips`: Tokyo food and art 5d, Lisbon budget solo 4d, Kyoto and Osaka 7d, Bali surf 6d,
New York museums 3d, Seoul culture 5d, Barcelona family 5d, Bangkok street food 4d, Copenhagen design 3d,
Taipei night markets 4d.

Checks reported per trip in `evals/results/<sha>.md`:

| Check | Pass condition | Lane |
|---|---|---|
| signals | at least 15 signals, at least 10 distinct places, every URL returns 200 | B |
| resolved | every stop resolves to a Google place_id | C |
| verified | at least 90 percent of stops pass exists, open, reachable, in_window | C |
| transit | 45 min or less between consecutive stops | C |
| bookable | at least one flight option and one stay option returned | D |
| gated | zero orders without `confirmed_by_user_at`; injected 500 yields exactly one order | D |
| loop | the full run completes with no unhandled exception, call log complete | A |

Each lane claims only its own rows, with evidence: PR link, test name, eval row, or a screenshot.

---

## 8. Demo and brief

**Two-minute demo, recorded by 15:40:**

| At | On screen |
|---|---|
| 0:00 | The questionnaire filled in for Tokyo. |
| 0:20 | Research signals appear with their sources and dates. |
| 0:40 | Draft itinerary, day by day. |
| 0:55 | The agent asks one question, the answer patches one stop. |
| 1:10 | Verifier flags a closed venue, swaps it, shows the transit time. |
| 1:30 | Flight and stay options, confirm, order number. |
| 1:45 | Injected provider failure, retry, still one order. |
| 1:55 | Calendar populated. |

**System and reliability brief** (Lane A writes, every lane fills its rows by 15:00):

1. What it does in three sentences, and the loop diagram.
2. External apps, what each is used for, which are sandbox.
3. Failure modes table: tool, failure, how it is detected, mitigation, test name.
4. Eval results table for the head SHA.
5. Known gaps and what was cut.
