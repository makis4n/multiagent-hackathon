# Demo script

Two minutes. Screen recording of the browser only, 1440x900, Tripia at http://localhost:8501 in a clean window,
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

## Timings

Measured on the merged main with Haiku drafting: the first wait (research plus draft) is 60 to 90 seconds, the
second (refine, resolve, verify, flight search) 50 to 60 seconds. That is more than two minutes of waiting, so
record the whole take and make one cut inside the first wait, while the loading bar is on screen. The narration
for that beat is one sentence; the cut lands between it and the next. Nothing else needs a cut.

Rehearse once right before the take so you know today's numbers and which stop to skip.

## The take

**0:00, the form.** Look at the form, then click Plan trip.

> Say I've got five days in Tokyo in November, two of us, we like food and art, and I don't want to spend a week
> on Reddit figuring out where to go. So I tell Tripia that, and I press go.

**0:08, the loading bar.** The bar fills and the tips rotate. Let one tip land before you talk over it.

> Right now it's reading. About a hundred posts from the last few weeks: YouTube vlogs, Reddit threads, all
> dated. Not a guidebook. What people are actually saying this month.

*Cut here if the wait runs long.*

**0:30, the draft appears.** Point at the source list in the sidebar, then scroll the draft slowly, once.

> There's the list it read from, every one with a date. And here's the first draft. Four stops a day, and every
> single one says which post it came from. Nothing is checked yet, and it's honest about that, see, they're all
> marked draft.

**0:50, the questions.** Read the first question aloud. In the "skip" question, type `skip:` and a place name copied
exactly from the first day. Leave the others blank. Click Check and finish the plan.

> Instead of guessing what I meant, it asks. I'll say skip this one, I've been. And that answer turns into an
> edit to the plan I'm already looking at, not a whole new plan.

**1:00, the second loading bar.** Talk over it. This is the part that matters, so slow down.

> Now the boring part that nobody does. Every stop goes to Google. Does the place exist. Is it open at that hour,
> on that day of the week. Can you actually get there from the one before. Twenty stops, a few hundred checks.

**1:20, the verified plan.** The photo banner, the 100% tile, the swaps beside it. Point at one swap.

> Done. This one's closed on Mondays, so it swapped it and tells me why. What's left is verified, all of it,
> and now the stops have faces.

**1:35, book the flight.** Scroll to Book. Click Book on the first flight. The reference appears.

> Flights are through Duffel, in test mode, and nothing gets booked until I click. Here's the bit I like: that
> call just failed halfway through, on purpose, and it retried. Still one booking. Every order carries a key, so
> a retry can never buy the same flight twice.

**1:50, the plan.** Scroll back to the top of the plan and stop.

> Ten test trips run through this exact loop and pass every check. That's the trip. Researched, checked, booked,
> with receipts.

## Notes for the speaker

- Say "Tripia" once, at the start. After that it's "it".
- Never read the screen aloud. Say what it means.
- The two waits are where people lose the room. Keep talking, keep the sentences short, and let the tip lines
  do some of the work: they are written to be read.
- If a swap did not happen this run, the line at 1:20 becomes: "Every stop passed first time, and it says so.
  On a busy day it swaps the closed ones and tells you why."
- The "Open calendar" button goes to a fake page. Do not click it on camera.

## If something breaks mid-take

Stop, fix, re-record. Never narrate around a broken screen. A take is two and a half minutes of real time; three
takes fit in fifteen.
