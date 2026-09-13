# trip-itinerary

Status: **C1 (draft) and C2 (places, verifier) Wai Kin; C3 (questions, refine, replace_failed) keaenlim; C4 (calendar) Codex**. See `PLAN.md` here.

Lane C. Four factories in `trip_itinerary/__init__.py`, each behind its own flag:

| factory | Protocol | flag | behind it |
| --- | --- | --- | --- |
| `build_resolver()` | `PlaceResolver` | `REAL_PLACES=1` | Google Places API (New): text search, place details with `regularOpeningHours` |
| `build_planner()` | `ItineraryPlanner` | `REAL_PLANNER=1` | Claude through `trip_core.llm.complete_json`; flat response schemas |
| `build_verifier(resolver)` | `Verifier` | `REAL_VERIFIER=1` | the four checks; Routes API `computeRoutes` for travel time |
| `build_calendar()` | `CalendarSink` | `REAL_CALENDAR=1` | Google Calendar API v3 through `CalendarExporter` and OAuth |

## The planner

`draft` lives in `trip_itinerary.draft`: one model call with a flat schema, then code that repairs days and
times. `questions`, `refine` and `replace_failed` live in `trip_itinerary.planner`: the model proposes, the code
decides. Every patch is applied to a throwaway copy first and dropped if it does not fit; invented signal ids are
stripped; more than eight patches in a round is a regeneration, so the extras go; a model failure returns no
patches and leaves the itinerary at the version the traveller saw.

Each planner call rebinds `planner.last_dropped`, one line per patch or question the code dropped. Read it
straight after the call, because the next call clears it.

`trip_core.fakes.FakeVerifier` is the reference for the checks: keep them, swap the travel time.

The calendar sink talks to the Google Calendar API v3 over plain HTTP with `httpx`, not the Google API client
library, so every test can record the traffic with `respx`. `google-auth-oauthlib` carries the OAuth flow that
mints the token. `build_calendar()` constructs a `CalendarExporter` with a `GoogleTokenProvider`; credentials are
read only when an itinerary is exported. Event times use the time zone in `TRIP_CALENDAR_TIMEZONE`, defaulting to
UTC when it is unset.
