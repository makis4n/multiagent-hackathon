# Cassettes

Recorded provider responses. Tests replay these through respx; CI never opens a socket.

Two kinds of file here, both legitimate:

- `youtube_search.json`, `youtube_videos.json`, `exa_search.json` are **hand-built stand-ins**, deliberately
  shaped to exercise one specific edge case each (a channel result with no video id, HTML entities in a title,
  a hidden like count, a result with no url, a null published date). A genuine recording is unlikely to contain
  all of these at once, so these stay synthetic on purpose; they are not a stopgap waiting to be replaced.
- `youtube_search_live.json`, `youtube_videos_live.json`, `exa_search_live.json` are **genuine recordings**,
  captured 2026-09-13 against real keys, checked for secrets before committing (the API key is sent in the
  request, never returned in the response body, so there was nothing to scrub). `test_a_genuine_recording_
  parses_without_incident` in each test file replays these: the point is proving our parsing matches the
  actual wire format, not just our reading of the docs.
- `reddit_search.json` remains a hand-built stand-in; `RedditSource` is not wired in, so there is no key to
  record a live response with yet.

## What was verified live, against real keys, 2026-09-13

| Finding | Result |
|---|---|
| YouTube `search.list` + `videos.list` against `YOUTUBE_API_KEY` | Works. One brief (Tokyo) returned 50 signals, 0 errors. |
| Exa `includeDomains: ["reddit.com"]` (and `["*.reddit.com"]`) against `EXA_API_KEY` | **Returns zero results, every time**, across multiple query phrasings and with or without a date filter. Not documented anywhere; found by direct testing. |
| Exa `includeDomains` against a control domain (`wikipedia.org`, `nytimes.com`) | Works normally, 5/5 results. So the reddit.com exclusion is specific to that domain, not a bug in our request shape. |
| Exa `includeDomains: ["x.com"]` and `["twitter.com"]` | **Also zero results, every time.** Same dead end as reddit.com; the two big social platforms both appear to be excluded from Exa's domain-filtered search. |
| Exa, no domain filter, four query phrasings that name Reddit or ask "what locals say" | Zero reddit.com URLs in any result set, not just zero under a domain filter. Reinforces the above rather than being separately conclusive on its own. |
| Both sources with `EXA_API_KEY`/`YOUTUBE_API_KEY` unset | Each degrades to an empty list with no exception; the exception never reaches `CallLog`. |

The Exa finding changed the design: `ExaSource` no longer sends `includeDomains`. It is general open-web
travel content (`web.py`), not a Reddit or X/Twitter channel. See the docstring at the top of `web.py`. Getting
genuine social-platform content requires either that platform's own API (Reddit's needs approval we do not
have; X's current tiers are effectively paid, unverified further since Exa already failed the same way for
free) or a different provider entirely.

## What was verified against the live docs (before keys existed)

| Shape | Verified | Source |
|---|---|---|
| `GET https://www.googleapis.com/youtube/v3/search`, params `part` `q` `type` `order` `publishedAfter` `maxResults` `key` | yes | developers.google.com/youtube/v3/docs/search/list |
| search.list response `items[].id.videoId`, `items[].snippet.{title,description,publishedAt,channelTitle}` | yes | same |
| search.list quota: **1 unit, and a bucket capped at 100 calls per day** | yes | same |
| `GET https://www.googleapis.com/youtube/v3/videos`, `part=statistics`, comma-separated `id`, quota 1 unit | yes | developers.google.com/youtube/v3/docs/videos/list |
| videos.list `statistics.{viewCount,likeCount,commentCount}` | yes | same |
| `POST https://api.exa.ai/search`, header `x-api-key`, body `query` `numResults` `startPublishedDate` `contents.text` | yes | exa.ai/docs/reference/search |
| Exa response `results[].{id,title,url,publishedDate,author,text}`, and that there is **no** `score` field | yes | same |

## What was assumed, not verified

- That YouTube returns counts as strings and omits `likeCount` when an uploader hides likes. The docs name the
  fields but do not state the type or the omission. The code tolerates both a string and a missing key.
- That YouTube titles arrive HTML-escaped (`&amp;`, `&#39;`). The code unescapes defensively either way.
- That Exa's `publishedDate` can be null. The code treats a missing date as unknown rather than failing.

Resolved: Exa's per-search price is not a placeholder any more. The live recording shows `costDollars.total`
of $0.007 for a 10-result neural search with `contents.text`. Two queries per brief, ten eval trips, is $0.14
a run, worth knowing before `make evals` runs on a loop.

## Place extraction: heuristic first, then a model refinement pass

The heuristic in `places.py` is tuned against the curated `tokyo` fixture, whose titles are clean prose with
one obvious proper noun each. Real YouTube titles are Title Case or ALL CAPS clickbait ("THE ULTIMATE ... GUIDE
｜30 MUST-VISIT SPOTS"), where casing cannot distinguish a place from a filler word. Fixed on 2026-09-13: a
stopword now breaks a run even when capitalised, a hyphenated compound ("must-visit") is checked part by part,
and a non-whitespace gap (an emoji, a pipe) breaks a run too. That alone still leaves webpage boilerplate and
sponsor mentions (nav-menu words, "Squarespace") that a keyword list cannot see through.

`extract_llm.py` (also 2026-09-13) adds a best-effort Gemini Flash-Lite pass on top, applied in `youtube.py`
and `web.py` only, never in `reddit.py`: Reddit's Responsible Builder Policy restricts sharing post data with
third-party AI, and neither YouTube nor Exa content carries that restriction. One batched call per source per
brief refines up to 40 signals at once. On a live Tokyo run this took the combined distinct-place count from
226 (heuristic alone) to 107, with the sponsor names and clickbait fragments gone. Any failure, no key, a rate
limit, a malformed answer, falls back to the heuristic's own result signal by signal; a source's `search()`
still never raises because of it.

The bug worth knowing about, because it was easy to get backwards: an empty list from the model is a real
answer ("nothing specific in this title"), not a miss. The first version of this code only trusted a
*non-empty* model answer and silently kept the old heuristic guess whenever the model correctly said there was
nothing there, which defeated most of the point. `test_an_explicit_empty_answer_clears_the_heuristic_guess`
guards this.
