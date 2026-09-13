# Cassettes

Recorded provider responses. Tests replay these through respx; CI never opens a socket.

Every file here is still a **hand-built stand-in**, shaped to the provider's documented response format, not a
real recording, even though real keys now exist. Swapping in genuine recordings is still open; scrub any real
one before committing, a token or key must never land in git.

## What was verified live, against real keys, 2026-09-13

| Finding | Result |
|---|---|
| YouTube `search.list` + `videos.list` against `YOUTUBE_API_KEY` | Works. One brief (Tokyo) returned 50 signals, 0 errors. |
| Exa `includeDomains: ["reddit.com"]` (and `["*.reddit.com"]`) against `EXA_API_KEY` | **Returns zero results, every time**, across multiple query phrasings and with or without a date filter. Not documented anywhere; found by direct testing. |
| Exa `includeDomains` against a control domain (`wikipedia.org`, `nytimes.com`) | Works normally, 5/5 results. So the reddit.com exclusion is specific to that domain, not a bug in our request shape. |
| Both sources with `EXA_API_KEY`/`YOUTUBE_API_KEY` unset | Each degrades to an empty list with no exception; the exception never reaches `CallLog`. |

The Exa finding changed the design: `ExaSource` no longer sends `includeDomains`. It is general open-web
travel content (`web.py`), not a Reddit channel. See the docstring at the top of `web.py`.

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
- Exa's per-search price. `costDollars` in the cassette is a placeholder.

## Known limitation: place extraction on real titles

The heuristic in `places.py` is tuned against the curated `tokyo` fixture, whose titles are clean prose with
one obvious proper noun each. Real YouTube titles are Title Case or ALL CAPS clickbait ("THE ULTIMATE ... GUIDE
｜30 MUST-VISIT SPOTS"), where casing cannot distinguish a place from a filler word. Fixed on 2026-09-13: a
stopword now breaks a run even when capitalised, a hyphenated compound ("must-visit") is checked part by part,
and a non-whitespace gap (an emoji, a pipe) breaks a run too. Residual false positives remain on live data
(a channel name, a lone country name) since there is no ceiling on distinguishing "a proper noun" from
"a place" without a model, which was deliberately not used here. Not toxic, just occasional noise.
