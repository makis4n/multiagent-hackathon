# Cassettes

Recorded provider responses. Tests replay these through respx; CI never opens a socket.

`reddit_search.json` is currently a **hand-built stand-in** shaped to Reddit's listing format, not a real
recording. Replace it with a real response as soon as credentials exist:

```sh
uv run python -m trip_research.record reddit > packages/research/tests/cassettes/reddit_search.json
```

Scrub before committing. A token response carries a live `access_token`; it must never land in git.
