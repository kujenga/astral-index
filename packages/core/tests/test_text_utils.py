"""Tests for text_utils: Jaccard, title_similarity, NON_JOURNALISM_RE."""

from __future__ import annotations

from astral_core.text_utils import NON_JOURNALISM_RE, _token_jaccard, title_similarity


class TestTokenJaccard:
    def test_identical_titles(self):
        assert _token_jaccard("SpaceX launches rocket", "SpaceX launches rocket") == 1.0

    def test_no_overlap(self):
        assert (
            _token_jaccard("SpaceX launches rocket", "NASA discovers exoplanet") == 0.0
        )

    def test_partial_overlap(self):
        jac = _token_jaccard(
            "Falcon 9 launches 29 Starlink satellites",
            "Deployment of 29 Starlink satellites confirmed",
        )
        # 3 content words overlap, 5 don't
        assert 0.3 < jac < 0.8

    def test_stopwords_ignored(self):
        """Stopwords like 'the', 'of', 'in' don't count toward overlap."""
        jac = _token_jaccard("the launch of the rocket", "a launch of a satellite")
        # Only "launch" overlaps; "rocket" vs "satellite" differ
        assert jac < 0.5

    def test_empty_string(self):
        assert _token_jaccard("", "something") == 0.0
        assert _token_jaccard("something", "") == 0.0

    def test_only_stopwords(self):
        assert _token_jaccard("the of in", "the of in") == 0.0


class TestTitleSimilarity:
    def test_near_identical_uses_levenshtein(self):
        """Punctuation-only diff -> high Levenshtein."""
        sim = title_similarity(
            "Watch the Starlink launch live!", "Watch the Starlink launch live"
        )
        assert sim >= 0.9

    def test_same_event_different_wording(self):
        """Same event, different phrasing -> Jaccard kicks in."""
        sim = title_similarity(
            "Falcon 9 launches Starlink Group 12 mission",
            "Starlink Group 12 deployment after Falcon 9 launch",
        )
        assert sim >= 0.5

    def test_different_stories_same_domain(self):
        """Different events sharing domain words -> low similarity."""
        sim = title_similarity(
            "SpaceX launches crew to ISS",
            "SpaceX Starship completes orbital test",
        )
        assert sim < 0.7

    def test_completely_unrelated(self):
        sim = title_similarity(
            "NASA budget update for 2026", "Best AI games to play this weekend"
        )
        assert sim < 0.3

    def test_identical(self):
        assert title_similarity("SpaceX Starship", "SpaceX Starship") == 1.0


class TestNonJournalismRe:
    def test_word_search(self):
        assert NON_JOURNALISM_RE.search("Try this word search puzzle!")

    def test_best_ai_games(self):
        assert NON_JOURNALISM_RE.search("Best AI games to play in 2026")

    def test_crossword(self):
        assert NON_JOURNALISM_RE.search("Daily crossword: March 14")

    def test_top_games(self):
        assert NON_JOURNALISM_RE.search("Top 10 games for space fans")

    def test_quiz(self):
        assert NON_JOURNALISM_RE.search("Space trivia quiz")

    def test_normal_headline_not_matched(self):
        assert (
            NON_JOURNALISM_RE.search("SpaceX launches Starship on orbital test flight")
            is None
        )

    def test_puzzle_in_article_context(self):
        """'puzzle' as a standalone word matches even in longer titles."""
        assert NON_JOURNALISM_RE.search("Found a negative film puzzle from the 1960s")

    def test_best_video_games(self):
        assert NON_JOURNALISM_RE.search("Best video games set in space")
