# Demo script

Two minutes, one take, recorded by 15:40 PT. Screen recording of the browser only, 1440x900, the Streamlit page
at http://localhost:8501 in a clean window. No terminal on screen. Narration in the present tense: say what the
agent is doing, not what we built.

## Setup, before recording

```sh
git pull --rebase origin main
cp .env.example .env            # fill the keys; set the REAL_* flags that are green in evals/results
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

| at | on screen | say |
| --- | --- | --- |
| 0:00 | The form, filled. Click Plan trip. | "Five days in Tokyo for two people who like food and art." |
| 0:15 | "What people are saying" fills with sources and dates. | "It reads what people posted recently on Reddit and YouTube, with dates, not a guidebook." |
| 0:35 | The draft, day by day, status draft. | "First draft. Every stop cites the post it came from. Nothing is checked yet." |
| 0:50 | The questions. Leave "skip: Shibuya Sky", answer one more. Click Check and finish. | "It asks a few things instead of guessing. Answers become edits, never a rewrite." |
| 1:05 | The warning: a venue closed at that hour, swapped. Verified 100%. | "Every stop is checked against Google: does it exist, is it open then, can you get there in time. This one was closed, so it swapped it." |
| 1:25 | Book. Click Book on the flight. The order appears once. | "Flights through Duffel, in test mode. Nothing is booked until I click. That call failed at the provider and retried: one booking, not two, because every order carries an idempotency key." |
| 1:40 | The order line on screen, with its Duffel reference. | "Stays would go the same way; Duffel Stays needs a commercial agreement, so today it's flights." |
| 1:52 | Open calendar. | "And it's in the calendar." |

The injected failure hits the first order call of the session, which is the flight click.

## If something breaks mid-take

Stop, fix, re-record. Never narrate around a broken screen. The freeze is 15:00; the recording window is 40
minutes, which is enough for three takes.
