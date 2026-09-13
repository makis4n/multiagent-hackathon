"""The extractor is pure, so these run with no network, no key and no model."""

from __future__ import annotations

import json
from pathlib import Path

from trip_research.places import MAX_PLACES, extract_places

FIXTURE = Path(__file__).parents[3] / "packages" / "core" / "trip_core" / "fixtures" / "tokyo.json"


def test_the_fixture_titles_still_yield_their_labelled_place() -> None:
    """17 of 18. The miss is tk-06, whose label "Kappabashi Kitchen Town" is richer than its own title."""
    signals = json.loads(FIXTURE.read_text())["signals"]
    hits = [
        signal["places_mentioned"][0] in extract_places(signal["title"], signal["excerpt"], "Tokyo")
        for signal in signals
    ]
    assert sum(hits) >= 17


def test_the_fixture_clears_the_eval_bar_of_ten_distinct_places() -> None:
    signals = json.loads(FIXTURE.read_text())["signals"]
    found = {place for signal in signals for place in extract_places(signal["title"], signal["excerpt"], "Tokyo")}
    assert len(found) >= 10


def test_the_destination_alone_is_never_a_place() -> None:
    assert "Tokyo" not in extract_places("Tokyo is great", "I love Tokyo", "Tokyo")


def test_a_longer_name_containing_the_destination_survives() -> None:
    assert "Tokyo National Museum" in extract_places("Tokyo National Museum is worth it", "", "Tokyo")


def test_a_generic_noun_alone_is_dropped() -> None:
    assert extract_places("The Museum was closed", "", "Tokyo") == []


def test_a_generic_noun_inside_a_longer_name_survives() -> None:
    """The bug this guards: stripping "Museum" off the tail collapsed "Mori Art Museum" to "Mori"."""
    assert "Mori Art Museum" in extract_places("Mori Art Museum current show", "", "Tokyo")
    assert "Tsukiji Outer Market" in extract_places("Tsukiji Outer Market at 7am", "", "Tokyo")


def test_camel_case_names_survive() -> None:
    assert "teamLab Planets" in extract_places("teamLab Planets vs Borderless", "", "Tokyo")


def test_a_hyphenated_name_survives() -> None:
    assert "Daikanyama T-Site" in extract_places("Daikanyama T-Site is the best bookshop", "", "Tokyo")


def test_a_lowercase_prefix_before_a_capital_is_not_a_name() -> None:
    """ "anti-Shibuya" is a compound, not a place. teamLab is, because it has no hyphen before the capital."""
    assert extract_places("Koenji: the anti-Shibuya", "", "Tokyo") == ["Koenji"]


def test_and_does_not_fuse_two_neighbouring_names() -> None:
    found = extract_places("Kichijoji and Inokashira Park for a slow Sunday", "", "Tokyo")
    assert "Kichijoji" in found and "Inokashira Park" in found


def test_results_are_deduped_and_capped() -> None:
    found = extract_places("Ueno Park", "Ueno Park, Ueno Park, Asakusa, Ginza, Shinjuku, Ikebukuro", "Tokyo")
    assert found.count("Ueno Park") == 1
    assert len(found) <= MAX_PLACES


def test_empty_text_yields_nothing() -> None:
    assert extract_places("", "", "Tokyo") == []
