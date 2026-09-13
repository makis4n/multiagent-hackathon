"""Lane B. YouTube and web search to typed Signals."""

from trip_core.tools import ResearchSource
from trip_research.web import ExaSource
from trip_research.youtube import YouTubeSource


def build_sources() -> list[ResearchSource]:
    """The real sources, one per provider. Selected by REAL_RESEARCH=1.

    RedditSource exists and is tested but is deliberately not wired in: Reddit's Responsible Builder Policy
    requires explicit approval before using their Data API, which we do not have. Reddit content still reaches
    the trip through ExaSource, which is scoped to reddit.com and carries its own licence to serve it.
    """
    return [YouTubeSource(), ExaSource()]
