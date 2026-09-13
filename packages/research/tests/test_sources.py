"""What REAL_RESEARCH=1 actually wires into the loop."""

from __future__ import annotations

import trip_research
from trip_research.web import ExaSource
from trip_research.youtube import YouTubeSource


def test_build_sources_returns_youtube_and_web() -> None:
    sources = trip_research.build_sources()
    assert [type(source) for source in sources] == [YouTubeSource, ExaSource]


def test_source_names_are_the_stable_log_labels() -> None:
    """These become research.<name> in logs/calls.jsonl, which the evals read. Renaming one breaks the evals."""
    assert [source.name for source in trip_research.build_sources()] == ["youtube", "web"]


def test_reddit_is_not_wired_in() -> None:
    """Deliberate: Reddit's Responsible Builder Policy requires approval we do not have."""
    assert all(source.name != "reddit" for source in trip_research.build_sources())
