"""Place-name extraction from free text. Deterministic, no model.

Heuristic rather than an LLM on purpose: Reddit's Responsible Builder Policy restricts sharing post data with
third-party AI, and a pure function is testable offline with no key and no quota.
"""

from __future__ import annotations

import re

MAX_PLACES = 4
MIN_NAME_CHARS = 3
MAX_NAME_WORDS = 6
TOKEN = re.compile(r"[A-Za-z][A-Za-z'’-]*")
CAMEL = re.compile(r"^[a-z]+[A-Z]")

# "and" is deliberately absent: it fuses two neighbouring names ("Kichijoji and Inokashira Park") into one.
CONNECTORS = {"of", "the", "de", "du", "des", "la", "le", "del", "di", "da", "van", "von"}

# Function words, sentence starters and forum furniture. Stripped from the edges of a run.
STOP = {
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "i",
    "we",
    "you",
    "they",
    "he",
    "she",
    "it",
    "me",
    "us",
    "them",
    "my",
    "our",
    "your",
    "his",
    "her",
    "their",
    "a",
    "an",
    "the",
    "and",
    "but",
    "or",
    "if",
    "so",
    "as",
    "at",
    "in",
    "on",
    "to",
    "for",
    "from",
    "with",
    "near",
    "this",
    "that",
    "these",
    "those",
    "there",
    "here",
    "then",
    "than",
    "too",
    "very",
    "just",
    "also",
    "still",
    "what",
    "where",
    "when",
    "why",
    "how",
    "who",
    "which",
    "whose",
    "whom",
    "went",
    "got",
    "get",
    "go",
    "going",
    "gone",
    "did",
    "do",
    "does",
    "done",
    "was",
    "were",
    "is",
    "are",
    "be",
    "had",
    "has",
    "have",
    "would",
    "could",
    "should",
    "will",
    "can",
    "might",
    "must",
    "book",
    "booked",
    "best",
    "worst",
    "worth",
    "skip",
    "skipped",
    "avoid",
    "love",
    "loved",
    "like",
    "liked",
    "hate",
    "pick",
    "edit",
    "update",
    "op",
    "tldr",
    "tl",
    "dr",
    "nsfw",
    "reddit",
    "subreddit",
    "youtube",
    "vlog",
    "video",
    "guide",
    "travel",
    "trip",
    "itinerary",
    "tour",
    "tourist",
    "tourists",
    "visit",
    "visiting",
    "visited",
    "day",
    "days",
    "week",
    "weeks",
    "weekend",
    "month",
    "months",
    "year",
    "years",
    "hour",
    "hours",
    "morning",
    "afternoon",
    "evening",
    "night",
    "nights",
    "today",
    "tomorrow",
    "yesterday",
    "early",
    "late",
    "pro",
    "tip",
    "tips",
    "note",
    "notes",
    "warning",
    "heads",
    "psa",
    "help",
    "question",
    "questions",
    "first",
    "second",
    "third",
    "last",
    "next",
    "one",
    "two",
    "three",
    "four",
    "five",
    "some",
    "any",
    "every",
    "no",
    "not",
    "never",
    "always",
    "really",
    "actually",
    "honestly",
    "definitely",
    "probably",
    "maybe",
    "closed",
    "open",
    "combined",
    "quiet",
    "small",
    "large",
    "great",
    "good",
    "bad",
    "nice",
    "windy",
    "sunny",
    "cash",
    "card",
    "free",
    "cheap",
    "expensive",
    "vintage",
    "stepping",
    "twenty",
    "thirty",
    "cat",
    "dogs",
    # Clickbait titles, not sentences: absent from the curated fixture, common in real YouTube titles.
    "ultimate",
    "top",
    "spot",
    "spots",
    "secret",
    "secrets",
    "hidden",
    "famous",
    "popular",
    "viral",
    "trending",
    "everything",
    "everywhere",
    "exist",
    "literally",
    "insane",
    "amazing",
    "incredible",
    "awesome",
    "perfect",
    "complete",
    "honest",
    "imagine",
    "try",
    "tried",
    "things",
    "thing",
    "feed",
    "published",
    "posted",
}

# Not a place on their own, but legitimate inside a longer name: "Museum" no, "Mori Art Museum" yes.
# These are never stripped from a run's edge; a run made only of these is dropped whole.
GENERIC = {
    "museum",
    "museums",
    "park",
    "parks",
    "market",
    "markets",
    "temple",
    "temples",
    "shrine",
    "shrines",
    "garden",
    "gardens",
    "valley",
    "sky",
    "tower",
    "bridge",
    "hall",
    "gallery",
    "centre",
    "center",
    "station",
    "airport",
    "hotel",
    "hostel",
    "cafe",
    "bar",
    "bars",
    "restaurant",
    "restaurants",
    "shop",
    "shops",
    "street",
    "streets",
    "district",
    "area",
    "areas",
    "neighbourhood",
    "neighborhood",
    "city",
    "town",
    "place",
    "food",
    "art",
    "coffee",
    "lunch",
    "dinner",
    "breakfast",
    "brunch",
    "drinks",
    "shopping",
    "walk",
    "walks",
    "kitchen",
    "outer",
    "inner",
    "upper",
    "lower",
    "north",
    "south",
    "east",
    "west",
    "old",
    "new",
}


def _is_name_like(token: str) -> bool:
    """Uppercase first letter, or camelCase like teamLab. A hyphen before the capital (anti-Shibuya) does not."""
    if token[0].isupper():
        return True
    return bool(CAMEL.match(token)) and "-" not in token


CONTRACTION = re.compile(r"['’](s|re|ve|ll|d|m)$|n['’]t$")


def _is_stopword(lowered: str) -> bool:
    """`lowered` itself, a contraction of one ("that's"), or every part of a hyphenated compound is one."""
    if lowered in STOP or CONTRACTION.sub("", lowered) in STOP:
        return True
    parts = lowered.split("-")
    return len(parts) > 1 and all(part in STOP for part in parts)


def _runs(text: str) -> list[list[str]]:
    """Consecutive name-like tokens. A stopword breaks a run even in Title Case: a marketing headline
    capitalises every word, so casing alone cannot tell "Guide" from "Ginza" mid-run, only STOP can. A gap
    that is not plain whitespace (a pipe, an emoji, a bracket) also breaks a run: two title segments either
    side of a separator are not one name just because nothing lowercase stood between them. A lowercase
    connector is still allowed inside a run, just never at its edges."""
    runs: list[list[str]] = []
    current: list[str] = []
    pending: list[str] = []
    cursor = 0
    for match in TOKEN.finditer(text):
        gap = text[cursor : match.start()]
        cursor = match.end()
        if gap and not gap.isspace() and current:
            runs.append(current)
            current, pending = [], []
        token = match.group(0)
        lowered = token.lower()
        if _is_name_like(token) and not _is_stopword(lowered):
            current.extend(pending)
            pending = []
            current.append(token)
        elif current and lowered in CONNECTORS:
            pending.append(token)
        else:
            if current:
                runs.append(current)
            current, pending = [], []
    if current:
        runs.append(current)
    return runs


def _clean(run: list[str]) -> str | None:
    while run and _is_stopword(run[0].lower()):
        run = run[1:]
    while run and _is_stopword(run[-1].lower()):
        run = run[:-1]
    if not run or len(run) > MAX_NAME_WORDS:
        return None
    name = " ".join(run)
    if len(name) < MIN_NAME_CHARS or all(word.lower() in STOP | GENERIC for word in run):
        return None
    return name


def extract_places(title: str, excerpt: str, destination: str) -> list[str]:
    """Named places mentioned in a signal, title first, deduped, capped. The destination alone never counts."""
    blocked = {destination.lower(), *(part.lower() for part in destination.split() if len(part) > MIN_NAME_CHARS)}
    found: list[str] = []
    for text in (title, excerpt):
        for run in _runs(text):
            name = _clean(run)
            if name is None or name.lower() in blocked:
                continue
            if name not in found:
                found.append(name)
    return found[:MAX_PLACES]
