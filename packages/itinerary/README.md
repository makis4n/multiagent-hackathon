# trip-itinerary

Status: **owner Lane C (keaenlim)**.

Lane C. Four factories in `trip_itinerary/__init__.py`, each behind its own flag:

| factory | Protocol | flag | behind it |
| --- | --- | --- | --- |
| `build_resolver()` | `PlaceResolver` | `REAL_PLACES=1` | Google Places API (New): text search, place details with `regularOpeningHours` |
| `build_planner()` | `ItineraryPlanner` | `REAL_PLANNER=1` | Gemini through `trip_core.llm.complete_json`; flat response schemas |
| `build_verifier(resolver)` | `Verifier` | `REAL_VERIFIER=1` | the four checks; Routes API `computeRoutes` for travel time |
| `build_calendar()` | `CalendarSink` | `REAL_CALENDAR=1` | Google Calendar API v3 |

`trip_core.fakes.FakeVerifier` is the reference for the checks: keep them, swap the travel time.
