# Demo script

Two minutes of finished video, two cuts. Screen recording of the browser only, 1440x900, Tripia at http://localhost:8501 in a clean window,
sidebar open. No terminal on screen. Talk in the present tense about what it is doing, not about what we built.
Sound like you are showing a friend, not reading a spec.

## Setup, before recording

```sh
git pull --rebase origin main
make check && make fixture      # both green, or do not record
make ui
```

`.env` needs every real flag on (`REAL_RESEARCH`, `REAL_PLANNER`, `REAL_PLACES`, `REAL_VERIFIER`, `REAL_BOOKING`)
and `INJECT_BOOKING_FAILURE=1`. Reload the page once after starting the server. Check the Duffel test balance
covers two rehearsals and the take: each run books one sandbox flight of roughly 1,000 to 2,000 EUR.

## The brief

The form opens on it already: Tokyo (TYO), from Stockholm Arlanda (ARN), 12 to 16 November, two travellers,
150 EUR a day, food and art selected. Do not touch it except to press Plan trip.
