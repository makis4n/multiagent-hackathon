# trip-itinerary

Status: **C1 (planner) and C2 (places, verifier) Wai Kin; C4 (calendar) Codex**. C3 is issue #14. See `PLAN.md` here.

Lane C. Four factories in `trip_itinerary/__init__.py`, each behind its own flag:

| factory | Protocol | flag | behind it |
| --- | --- | --- | --- |
| `build_resolver()` | `PlaceResolver` | `REAL_PLACES=1` | Google Places API (New): text search, place details with `regularOpeningHours` |
| `build_planner()` | `ItineraryPlanner` | `REAL_PLANNER=1` | Claude through `trip_core.llm.complete_json`; flat response schemas |
| `build_verifier(resolver)` | `Verifier` | `REAL_VERIFIER=1` | the four checks; Routes API `computeRoutes` for travel time |
| `build_calendar()` | `CalendarSink` | `REAL_CALENDAR=1` | Google Calendar API v3 through `CalendarExporter` and OAuth |

`trip_core.fakes.FakeVerifier` is the reference for the checks: keep them, swap the travel time.

The calendar sink talks to the Google Calendar API v3 over plain HTTP with `httpx`, not the Google API client
library, so every test can record the traffic with `respx`. `google-auth-oauthlib` carries the OAuth flow that
mints the token. `build_calendar()` constructs a `CalendarExporter` with a `GoogleTokenProvider`; credentials are
read only when an itinerary is exported. Event times use the time zone in `TRIP_CALENDAR_TIMEZONE`, defaulting to
UTC when it is unset.
