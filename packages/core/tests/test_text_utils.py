"""Tests for text_utils: Jaccard, title_similarity, NON_JOURNALISM_RE."""

from __future__ import annotations

from astral_core.text_utils import (
    NON_INFORMATIONAL_RE,
    NON_JOURNALISM_RE,
    _token_jaccard,
    title_similarity,
)


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


class TestNonInformationalRe:
    def test_photo_of_the_day(self):
        assert NON_INFORMATIONAL_RE.search("Photo of the Day: Mars from Perseverance")

    def test_image_of_the_week(self):
        assert NON_INFORMATIONAL_RE.search("Image of the Week: Andromeda Galaxy")

    def test_astrophotography(self):
        assert NON_INFORMATIONAL_RE.search("Tips for astrophotography beginners")

    def test_stunning_image(self):
        assert NON_INFORMATIONAL_RE.search(
            "Stunning image of Jupiter captured by amateur"
        )

    def test_best_space_photos(self):
        assert NON_INFORMATIONAL_RE.search("Best space photos of 2026")

    def test_stargazing_guide(self):
        assert NON_INFORMATIONAL_RE.search("March stargazing guide: what to look for")

    def test_visible_tonight(self):
        assert NON_INFORMATIONAL_RE.search("ISS visible tonight over North America")

    def test_when_to_see(self):
        assert NON_INFORMATIONAL_RE.search("When to see the next meteor shower")

    def test_scifi_movie_review(self):
        assert NON_INFORMATIONAL_RE.search("New sci-fi movie review: Interstellar 2")

    def test_best_scifi_shows(self):
        assert NON_INFORMATIONAL_RE.search(
            "Best shows about space and sci-fi this year"
        )

    def test_podcast_episode(self):
        assert NON_INFORMATIONAL_RE.search("Space podcast episode 42: Mars update")

    def test_picture_of_the_week(self):
        assert NON_INFORMATIONAL_RE.search("ESA picture of the week: aurora")

    def test_how_to_photograph(self):
        assert NON_INFORMATIONAL_RE.search("How to photograph the Milky Way")

    def test_camera_gear_for_night_sky(self):
        assert NON_INFORMATIONAL_RE.search("Best camera gear for night sky photography")

    def test_normal_headline_not_matched(self):
        assert (
            NON_INFORMATIONAL_RE.search(
                "SpaceX launches Starship on orbital test flight"
            )
            is None
        )

    def test_technical_article_not_matched(self):
        assert (
            NON_INFORMATIONAL_RE.search("NASA selects new lunar lander design") is None
        )

    def test_science_discovery_not_matched(self):
        assert (
            NON_INFORMATIONAL_RE.search("JWST discovers high-redshift galaxy at z=14")
            is None
        )

    def test_policy_article_not_matched(self):
        assert (
            NON_INFORMATIONAL_RE.search("Congress approves NASA budget increase")
            is None
        )

    def test_launch_report_not_matched(self):
        assert (
            NON_INFORMATIONAL_RE.search("Rocket Lab Electron launches radar satellite")
            is None
        )
