# Calendar export: the trip lands in Google Calendar

Lane C, `packages/itinerary`. Branch `lane/c-calendar-export`, cut from main after the refinement PR merges. Flag `REAL_CALENDAR`.

## Goal
The finished itinerary becomes a real Google Calendar the traveller can open on their phone, one event per stop,
and exporting the same trip twice leaves one event per stop rather than two.

## Contract impact
None. `CalendarSink.export(itinerary, brief) -> str` exists, the `REAL_CALENDAR` flag exists, and `registry.py`
already calls `build_calendar()`. No edit to `packages/core`.

Two changes outside the package, both small, both worth a line in the team chat before the PR:

- `.env.example` gains `TRIP_CALENDAR_TIMEZONE=` under the Lane C group, empty, defaulting to UTC in code.
  `GOOGLE_CALENDAR_CREDENTIALS_JSON` is already declared.
- `.gitignore` gains the cached OAuth token path, so a token can never be committed.

`packages/itinerary/pyproject.toml` gains `httpx` and `google-auth-oauthlib` as runtime dependencies, which
relocks `uv.lock`. Calendar API v3 is called over plain HTTP so every test can record it with `respx`.

## Behaviour

`CalendarSink.export(itinerary, brief)`:

1. Creates one secondary calendar per trip, named `<destination> <start_date>`, and returns the URL that opens
   it. Its time zone is `TRIP_CALENDAR_TIMEZONE`, defaulting to UTC. Confirm the create-calendar endpoint, the
   event fields and the shareable URL shape in the Calendar API v3 docs before writing the call.
2. Writes one event per stop: the place name as the title, the stop's `why` and the itinerary id in the
   description, and start and end built from the day's date and the stop's times, sent as a local date-time plus
   the calendar's time zone rather than as an offset.
3. Reuses the same calendar on a second export of the same itinerary id, found by name, instead of creating a
   second one.
4. Gives every event an id derived from the itinerary id and the stop id, so a second export of the same trip
   updates each event in place. One export or five, the calendar holds one event per stop.
5. Deletes the events of stops that are no longer in the itinerary before writing the current ones, so a stop
   removed by a patch does not linger on the calendar after a re-export.
6. Exports every stop, including one the verifier failed, with the title prefixed `Unverified: ` and the reason
   in the description. Nothing the traveller planned disappears silently.
7. Reads `GOOGLE_CALENDAR_CREDENTIALS_JSON` at the first call, not at import, and raises `ToolError` naming
   `.env` when it is missing. The token is cached to the gitignored path and reused; the interactive OAuth flow
   runs only when there is no valid cached token.
8. 429 and 5xx raise `RetryableError`. 401 and 403 raise `ToolError` telling the user to re-authorise. Every
   other non-2xx raises `ToolError` with the status and the Google error status string, never the response body
   and never the token. No bare `except`.

## Failure handling

| Call | Failure | Detected by | What the code does |
| --- | --- | --- | --- |
| create calendar | 429 or 5xx | status code | `RetryableError`, one retry, then it surfaces |
| create calendar | 401 or 403 | status code | `ToolError` naming re-authorisation, no token in the message |
| insert event | id already exists | 409 | falls back to an update of that event id, which is the idempotency path |
| insert event | one event of many fails | status per response | the export raises with the failing stop id, after the events already written stay written |
| delete a stale event | 404 | status code | treated as already gone, not an error |
| any | no credentials | env lookup at call time | `ToolError` naming `.env` |

## Tests that prove it

Offline, `respx` against responses recorded in `packages/itinerary/tests/cassettes/`. The OAuth flow never runs in
a test: the client takes a token provider, and the tests inject a stub that returns a fixed fake token.

| File and name | Plants | Asserts |
| --- | --- | --- |
| `tests/test_calendar.py::test_creates_a_calendar_and_returns_its_url` | recorded create and insert responses | the URL contains the calendar id, and the name carries the destination and start date |
| `tests/test_calendar.py::test_one_event_per_stop` | the tokyo fixture itinerary | one insert per stop, with the title, start, end and time zone of each |
| `tests/test_calendar.py::test_second_export_updates_instead_of_duplicating` | a full export, then the same export again | the second run issues updates, not new inserts, and the event count is unchanged |
| `tests/test_calendar.py::test_insert_conflict_falls_back_to_update` | a 409 on insert | one update follows and the export succeeds |
| `tests/test_calendar.py::test_removed_stop_is_deleted` | an itinerary with one stop patched out | a delete for that event id, and no delete for any surviving stop |
| `tests/test_calendar.py::test_unverified_stop_is_labelled` | a stop marked failed with a reason | the title is prefixed and the reason is in the description |
| `tests/test_calendar.py::test_status_codes` | 503, then 403, then 400 | `RetryableError`, then `ToolError` about re-authorising, then `ToolError` carrying the status and no body |
| `tests/test_calendar.py::test_missing_credentials_names_the_env_file` | no `GOOGLE_CALENDAR_CREDENTIALS_JSON` | `ToolError` mentioning `.env`, raised at the call and not at import |
| `tests/test_calendar.py::test_no_token_in_any_log_line` | a run with the call log attached | no log line contains the token or a request body |

The reliability claim is the second export. Watch it go red against a version that only inserts, then fix it.

## Out of scope

- Invites, reminders, colours, attendees and recurring events.
- Flight and stay bookings as calendar events. Stops only in this PR.
- A per-stop location field from the resolved place. It waits for the resolver, which is not in this branch.
- Deleting the calendar. A trip the traveller no longer wants is theirs to delete.

## Done when

- `make check` green
- `make fixture` green, unchanged on fakes
- `REAL_CALENDAR=1 uv run trip --fixture tokyo --auto-confirm` prints a calendar URL that opens a calendar
  holding one event per stop, and running it twice leaves the same number of events
- eval rows: none directly, the loop row must stay green with the flag on
- demo moment: at 1:55, the calendar is populated
