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

## Timings

The finished video is 2:00. The take runs about 3:00 in real time because the two waits are 60 to 90 seconds
(research plus draft, Haiku drafting) and 50 to 60 seconds (refine, resolve, verify, flight search). Each wait
keeps a short window on screen and loses the rest to one cut, made while the loading bar is up and nothing else
moves. The bar is at a different fill either side of the cut; nobody notices, the tip line changes anyway.

| segment | video time | screen time | what to do at the cut |
| --- | --- | --- | --- |
| Form and go | 0:00 to 0:10 | 10 s | |
| First wait, shown | 0:10 to 0:26 | 16 s of 60 to 90 | talk to the dash, stop dead, keep recording |
| Sources and draft | 0:26 to 0:50 | 24 s | |
| Question and answer | 0:50 to 1:02 | 12 s | |
| Second wait, shown | 1:02 to 1:22 | 20 s of 50 to 60 | same: talk to the dash, silence, keep recording |
| Verified plan | 1:22 to 1:38 | 16 s | |
| Book the flight | 1:38 to 1:52 | 14 s | |
| Close | 1:52 to 2:00 | 8 s | |

Rule for the cuts: the line spoken over a wait must be finished before the cut, and the next line starts only
when the result is on screen. The silence between them is what you cut, so there is never a word split in half.

Rehearse once right before the take so you know today's numbers and which stop to skip.

## The take

Two minutes of talking, no dead air. The word counts fit each slot at an easy pace, about 140 words a minute.
At the two cuts, stop at the full stop marked with a dash, keep recording in silence, and pick up the next
sentence once the result is on screen.

**0:00, the form.** Look at the form, then click Plan trip. Ten seconds.

> Five days in Tokyo in November, two of us, we like food and art, and I don't want to spend a week on
> Reddit working out where to go. So I tell Tripia that, and I press go.

**0:10, the loading bar.** Sixteen seconds on screen. Start talking as the bar appears.

> So right now it's out reading. About a hundred posts from the last few weeks. YouTube vlogs, Reddit threads,
> every one with a date on it. Not a guidebook from three years ago. What people are saying this month. —

**0:26, the draft.** Point at the source list in the sidebar, then scroll the draft slowly, once. Twenty-four
seconds.

> There it is. Down the side, everything it read, each with a source and a date. And here's the first draft.
> Four stops a day, and every stop tells you which post it came from, so you can click through and read it
> yourself. Nothing's verified yet, and it's honest about that. They're all marked draft.

**0:50, the question.** Read the skip question aloud. Type `skip:` and a place name copied exactly from the first
day. Leave the rest blank. Click Check and finish the plan. Twelve seconds.

> Instead of guessing what I meant, it asks. Anything to skip? Yeah, this one, I've been. And that becomes an
> edit to the plan I'm already looking at. It doesn't start over.

**1:02, the second loading bar.** Twenty seconds on screen. This is the part that matters, so slow down.

> Now the boring part, the part nobody actually does. Every stop goes off to Google. Does the place exist. Is
> it open at that hour, on that day of the week. Can you get there from the stop before it. Twenty stops, a
> few hundred checks, all of them. —

**1:22, the verified plan.** The photo banner, the 100% tile, the swaps beside it. Point at one swap. Sixteen
seconds.

> Done. And look, this one's closed on Mondays, so it swapped it for somewhere nearby and tells me why, right
> there. Everything left is verified, all of it, and the stops have faces now.

**1:38, book the flight.** Scroll to Book, click Book on the first flight, the reference appears. Fourteen
seconds.

> Flights go through Duffel, test mode, and nothing gets booked until I click. Here's the bit I like. That call
> just failed halfway, on purpose, and it retried. Still one booking. Every order carries a key, so a retry
> can never buy the same flight twice.

**1:52, close.** Scroll back to the top of the plan and stop on it. Eight seconds.

> Ten test trips run through this same loop and pass every check. So that's the trip. Researched, checked,
> booked, with receipts.

## Notes for the speaker

- Say "Tripia" once, at the start. After that it's "it".
- Never read the screen aloud. Say what it means.
- The two waits are where people lose the room. Keep talking to the dash, then stop dead. The silence after
  it is what gets cut; the tip lines on the bar carry the screen while you wait for the result.
- If a swap did not happen this run, the line at 1:22 becomes: "Every stop passed first time, and it says so.
  On a busy day it swaps the closed ones and tells you why."
- The "Open calendar" button goes to a fake page. Do not click it on camera.

## If something breaks mid-take

Stop, fix, re-record. Never narrate around a broken screen. A take is three minutes of real time; three takes and the
two cuts fit in twenty.
