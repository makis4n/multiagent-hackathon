# Demo script

Two minutes, one take, recorded by 15:40 PT. Screen recording of the browser only, 1440x900, the Streamlit page
at http://localhost:8501 in a clean window. No terminal on screen. Narration in the present tense: say what the
agent is doing, not what we built.

## Setup, before recording

```sh
git pull --rebase origin main
cp .env.example .env            # fill the keys, then: REAL_RESEARCH=1 REAL_PLANNER=1 REAL_PLACES=1 REAL_VERIFIER=1 REAL_BOOKING=1
echo INJECT_BOOKING_FAILURE=1 >> .env
make check && make fixture      # both green, or do not record
make ui
```

Reload the page once so the caption reads the real tools you expect plus "booking failure injected".

## The brief to type

| field | value |
| --- | --- |
| Destination | Tokyo |
| Flying from | ARN |
| Start, End | 2026-11-12, 2026-11-16 |
| Travellers | 2 |
| Budget | mid |
| Styles | food, art |

## Beats

Measured on real tools at 13:20 PT: research 12 s, draft 7 s, verification 22 s. Two waits, about 19 s and 22 s.
Talk through both; never stare at a spinner in silence. One take fits two minutes without cuts.

| at | do | on screen | say |
| --- | --- | --- | --- |
| 0:00 | Read the filled form, click Plan trip. | The brief. | "Five days in Tokyo for two people who like food and art. One form, then the agent works." |
| 0:10 | Wait, talking. | "Researching and drafting". | "It's reading about a hundred recent posts right now: YouTube vlogs and Reddit threads via web search, with dates. Not a guidebook, what people said this month." |
| 0:28 | Point at the source list. | "What people are saying", titles with source and date. | "Every source is dated. Then Gemini drafts from those, and only those." |
| 0:38 | Scroll the draft once. | Day tables, status draft. | "First draft. Every stop cites the post it came from. Nothing is checked yet, and it says so." |
| 0:48 | Answer one question: type `skip: ` plus a place name copied exactly from the draft. Click Check and finish. | The questions. | "It asks instead of guessing. An answer becomes an edit to the plan, never a rewrite." |
| 0:58 | Wait, talking. | "Refining and verifying every stop". | "Now every stop goes to Google: does the place exist, is it open at that hour on that weekday, can you get there in time from the previous stop. Twenty stops, a few hundred checks." |
| 1:20 | Point at the warnings. | Swaps and removals with reasons; Stops verified 100%. | "This museum closes Mondays, so it swapped it. This leg was too far, so it dropped the stop and says why. What's left is verified." |
| 1:35 | Click Book on the flight. | The order line with its reference. | "Flights through Duffel, test mode. Nothing is booked until I click. That call failed at the provider and retried; still one booking, because every order carries an idempotency key." |
| 1:50 | Scroll to the top of the plan. | The finished plan. | "Ten test trips run through this same loop and pass every check. That's the trip, verified, with receipts." |

The `skip:` answer must match a place name in the draft exactly, or nothing is removed. Pick one from the first
day's table before you start talking.

## If something breaks mid-take

Stop, fix, re-record. Never narrate around a broken screen. The freeze is 15:00; the recording window is 40
minutes, which is enough for three takes.
