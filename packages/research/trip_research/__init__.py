"""Lane B. Reddit, YouTube and web search to typed Signals."""

from trip_core.tools import ResearchSource


def build_sources() -> list[ResearchSource]:
    """The real sources, one per provider. Selected by REAL_RESEARCH=1."""
    raise NotImplementedError("Lane B: implement trip_research.build_sources()")
