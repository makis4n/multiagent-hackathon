# Tasks: calendar-export

- [x] 1. chore(itinerary): add httpx and google-auth-oauthlib to the package dependencies, declare TRIP_CALENDAR_TIMEZONE in .env.example, gitignore the cached token, relock
- [ ] 2. feat(itinerary): credentials and token provider, cached token reused, missing credentials raises ToolError naming .env, with its test
- [ ] 3. feat(itinerary): Calendar client over httpx with the status-code mapping to RetryableError and ToolError, with the recorded status test
- [ ] 4. feat(itinerary): create or reuse the trip calendar and return its URL, with the recorded create test
- [ ] 5. feat(itinerary): one event per stop from the day date, the stop times and the calendar time zone, with the per-stop test
- [ ] 6. feat(itinerary): stable event ids so a second export updates rather than duplicates, plus the 409 fallback, tests watched red first
- [ ] 7. feat(itinerary): delete the events of stops that are gone, and label an unverified stop rather than dropping it
- [ ] 8. feat(itinerary): wire build_calendar, update the README table, REAL_CALENDAR run green twice in a row
