# Lane C plan: itinerary and verification

Four factories in `trip_itinerary/__init__.py`, each behind its own flag. Build them in this order; each one is
demoable on its own with the others still fake. Cut C4 first, then C3, if time runs out.

| step | issue | flag | time | what the demo gains |
| --- | --- | --- | --- | --- |
| C1 planner: draft and questions | #4 | `REAL_PLANNER=1` | 45 min | a real agent drafting from real signals |
| C2 resolver and verifier | #5 | `REAL_PLACES=1`, `REAL_VERIFIER=1` | 60 min | every stop checked against Google; the closed-venue swap is real |
| C3 refine and replace_failed | #6 | (same planner) | 30 min | answers become patches; failed stops get real replacements |
| C4 calendar | #7 | `REAL_CALENDAR=1` | 30 min | the last beat of the demo |

The fakes in `trip_core/fakes.py` are the shape to copy: `FakePlanner` for C1 and C3, `FakeVerifier` for C2
(keep its four checks, swap the travel time). Run `make fixture` with your flag on after every step.

## C1: the planner (Gemini)

One class implementing `ItineraryPlanner`. Every model call goes through `trip_core.llm.complete_json` with a
flat pydantic schema. Convert to contract types in code; never ask the model for `Itinerary` directly (it has
dates, enums and nested lists the JSON schema translation rejects).

Response schemas, all flat:

```python
class DraftStop(BaseModel):
    day: int  # 0-based index into the trip dates
    start: str  # "10:00"
    end: str  # "12:00"
    place_name: str  # exactly as it appears in a signal when it came from one
    category: str  # food, sight, museum, walk, nightlife, shopping, nature, rest
    why: str  # one sentence naming what the signal said
    signal_ids: list[str]


class DraftItinerary(BaseModel):
    stops: list[DraftStop]
    notes: str


class Questions(BaseModel):
    questions: list[str]
```

`draft(brief, signals)`: prompt = the brief (destination, dates with weekdays, travellers, budget, styles,
answers so far) plus the signals as numbered lines `id | source | posted_at | title | places`. Ask for three
to four stops a day, 10:00 to 21:00, each citing signal ids, no two stops at the same place, a `place_name`
the resolver can search for ("Tsukiji Outer Market", not "the fish market"). Build `Itinerary` with one `Day`
per `brief.dates`, stop ids `stop-00`..., and drop any stop whose day is out of range.

`questions(brief, itinerary)`: prompt = brief plus the draft; ask for at most `MAX_QUESTIONS` short questions
whose answers would change the plan, skipping anything already in `brief.answers`.

Model: `model_main()` for draft, `model_fast()` for questions. Temperature 0.3 for the draft.

Test: one recorded call through `trip_core.cassette` (wrap the `complete_json` result with `.model_dump()`),
asserting the Tokyo fixture drafts five days with at least three stops each and every stop cites a signal id
that exists. Run it once with `RECORD=1`, commit the cassette.

## C2: resolver and verifier (Google Places and Routes)

Both use one key, `GOOGLE_MAPS_API_KEY`, with Places API (New) and Routes API enabled on the project; billing
must be on, the free credit covers the day. Verify the endpoints against the docs before building; the notes
below are the shape to check, not the reference.

`build_resolver()` returns a class with a dict cache keyed by place id:

- `resolve(name, near)`: `POST https://places.googleapis.com/v1/places:searchText`, headers `X-Goog-Api-Key`
  and `X-Goog-FieldMask: places.id,places.displayName,places.formattedAddress,places.location,`
  `places.regularOpeningHours,places.rating,places.priceLevel`, body `{"textQuery": f"{name}, {near}",`
  `"maxResultCount": 1}`. No result means `None`; that is the `exists` failure and is correct.
- `get(place_id)`: the cache, else `GET https://places.googleapis.com/v1/places/{id}` with the same field mask.
- Opening hours: Places gives `regularOpeningHours.periods[]` with `open.day` and `close.day` where **0 is
  Sunday**; the contract's `opening_hours` uses **0 = Monday**, so map `weekday = (day - 1) % 7`. A period
  with no `close` means open 24 hours. No `regularOpeningHours` at all means unknown: leave the dict empty so
  `is_open` returns None and the check passes with "hours unknown".
- Every response checks the status code; a 429 or 5xx raises `RetryableError`, anything else `ToolError`.

`build_verifier(resolver)`: copy `FakeVerifier.verify` and replace `travel_minutes` with Routes:
`POST https://routes.googleapis.com/directions/v2:computeRoutes`, header `X-Goog-FieldMask: routes.duration`,
body with `origin.location.latLng`, `destination.location.latLng`, `travelMode: "TRANSIT"`; `duration` comes
back as `"1234s"`. Cache by (from id, to id). If Routes fails for a leg, fall back to the straight-line estimate
and say so in the check detail. Keep the cap at `MAX_TRANSIT_MINUTES`.

Tests: one cassette per API (a Tsukiji search, one details call, one route), asserting the weekday mapping
and the duration parse. The weekday mapping is where the bug will be; plant a Sunday period and watch it land
on weekday 6.

## C3: refine and replace_failed

`refine(brief, itinerary, answers, signals)`: prompt = the itinerary with stop ids, the answers, the signals;
response schema:

```python
class PatchOp(BaseModel):
    op: str  # add, remove, move, replace
    stop_id: str | None
    target_day: int | None
    position: int | None
    new_stop: DraftStop | None


class Patches(BaseModel):
    ops: list[PatchOp]
```

Convert to `ItineraryPatch`; drop any op whose `stop_id` does not exist. Answers shaped `skip: <place>` must
become `remove` ops even without the model, so keep the fake's string rule as the first pass.

`replace_failed(brief, itinerary, report, signals)`: for each failed stop, prompt with the stop, its
`failure_reason`, the day, the neighbouring stops and the unused signal places; ask for one `replace` op per
failed stop, `remove` when nothing fits. Exclude skipped places (`trip_core.fakes.skipped_places`).

Test: plant a failed stop on a fixture draft and assert the patches apply through `apply_patch` and the stop is
gone or replaced; one cassette.

## C4: calendar

`build_calendar()`: `google-api-python-client` plus `google-auth-oauthlib`; `InstalledAppFlow` with scope
`https://www.googleapis.com/auth/calendar.events`, token cached in a gitignored `token.json`. One event per
stop on a calendar named "Trip agent" (create it once, keep the id in `.env`), `export` returns the calendar's
web URL. Idempotency: put the stop id in the event's `extendedProperties.private` and update rather than insert
when it already exists, so exporting twice does not double the events.

Test: a cassette of one insert; the request body shape is what matters.

## Handoff

Each step ends with: flag on, `make fixture` green, one cassette test, `make check` green, a PR that closes the
issue, and a chat line `C: LIVE — <what works, the flag to set>`. Fill your rows in `BRIEF.md` as you go:
the transit cap row is yours.
