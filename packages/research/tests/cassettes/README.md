# Cassettes

Recorded provider responses. Tests replay these through respx; CI never opens a socket.

Every file here is currently a **hand-built stand-in**, shaped to the provider's documented response format,
not a real recording. We have no API keys yet. Replace each one with a real response once keys exist, and
scrub it first: a token or key must never land in git.

## What was verified against the live docs

| Shape | Verified | Source |
|---|---|---|
| `GET https://www.googleapis.com/youtube/v3/search`, params `part` `q` `type` `order` `publishedAfter` `maxResults` `key` | yes | developers.google.com/youtube/v3/docs/search/list |
| search.list response `items[].id.videoId`, `items[].snippet.{title,description,publishedAt,channelTitle}` | yes | same |
| search.list quota: **1 unit, and a bucket capped at 100 calls per day** | yes | same |
| `GET https://www.googleapis.com/youtube/v3/videos`, `part=statistics`, comma-separated `id`, quota 1 unit | yes | developers.google.com/youtube/v3/docs/videos/list |
| videos.list `statistics.{viewCount,likeCount,commentCount}` | yes | same |
| `POST https://api.exa.ai/search`, header `x-api-key`, body `query` `numResults` `includeDomains` `startPublishedDate` `contents.text` | yes | exa.ai/docs/reference/search |
| Exa response `results[].{id,title,url,publishedDate,author,text}`, and that there is **no** `score` field | yes | same |

## What was assumed, not verified

- That YouTube returns counts as strings and omits `likeCount` when an uploader hides likes. The docs name the
  fields but do not state the type or the omission. The code tolerates both a string and a missing key.
- That YouTube titles arrive HTML-escaped (`&amp;`, `&#39;`). The code unescapes defensively either way.
- That Exa's `publishedDate` can be null. The code treats a missing date as unknown rather than failing.
- Exa's per-search price. `costDollars` in the cassette is a placeholder.
