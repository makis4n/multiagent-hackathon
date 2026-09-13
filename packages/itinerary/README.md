# trip-itinerary

Status: **owner Lane C (keaenlim)**.

Lane C. Four factories in `trip_itinerary/__init__.py`, each behind its own flag:

| factory | Protocol | flag | behind it |
| --- | --- | --- | --- |
| `build_resolver()` | `PlaceResolver` | `REAL_PLACES=1` | Google Places API (New): text search, place details with `regularOpeningHours` |
| `build_planner()` | `ItineraryPlanner` | `REAL_PLANNER=1` | Gemini through `trip_core.llm.complete_json`, flat response schemas, except `draft`, which delegates to `trip_core.fakes.FakePlanner` |
| `build_verifier(resolver)` | `Verifier` | `REAL_VERIFIER=1` | the four checks; Routes API `computeRoutes` for travel time |
| `build_calendar()` | `CalendarSink` | `REAL_CALENDAR=1` | Google Calendar API v3 |

## The planner

`questions`, `refine` and `replace_failed` are the model-backed members. `draft` is not: with `REAL_PLANNER=1`
the plan you first see is still the fake draft, refined by a real model. Do not read it as a real draft. The
real draft gets its own spec.

`build_resolver()`, `build_verifier()` and `build_calendar()` still raise `NotImplementedError`.

Each planner call rebinds `planner.last_dropped`, a list of one line per patch or question the code dropped:
over the cap, not applicable, a stray stop id, an invented signal id. Read it straight after the call, because
the next call clears it. It is not in the call log: those lines quote fragments of model output, and the loop
that would log them is Lane A's.

`trip_core.fakes.FakeVerifier` is the reference for the checks: keep them, swap the travel time.
