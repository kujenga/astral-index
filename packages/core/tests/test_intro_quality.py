"""Tests for the intro_quality heuristic scorer."""

from __future__ import annotations

from astral_core.scoring import intro_quality


def _make_output(
    introduction: str = "",
    sections: list[dict] | None = None,
) -> dict:
    """Build a minimal output dict for the scorer."""
    return {
        "introduction": introduction,
        "sections": sections or [],
    }


def _make_sections() -> list[dict]:
    """Sections with realistic titles and summaries."""
    return [
        {
            "heading": "Launch Vehicles",
            "items": [
                {
                    "title": "SpaceX Starship completes orbital flight",
                    "summary": (
                        "The spacecraft achieved a stable orbit for the"
                        " first time, reaching an altitude of 250 km"
                        " before a controlled deorbit burn."
                    ),
                    "item_id": "a1",
                    "source_name": "SpaceNews",
                },
                {
                    "title": "Rocket Lab Neutron enters final testing",
                    "summary": (
                        "Neutron's carbon composite fairing passed"
                        " structural load tests at the Wallops Island"
                        " facility ahead of a Q3 maiden flight."
                    ),
                    "item_id": "a2",
                    "source_name": "Ars Technica",
                },
            ],
        },
        {
            "heading": "Missions",
            "items": [
                {
                    "title": "Europa Clipper returns first ice data",
                    "summary": (
                        "Initial radar soundings reveal subsurface"
                        " liquid water pockets at depths of 15-20 km"
                        " beneath the Europan ice shell."
                    ),
                    "item_id": "b1",
                    "source_name": "NASA",
                },
            ],
        },
    ]


class TestIntroQualityMissing:
    def test_missing_intro_scores_zero(self):
        result = intro_quality(output=_make_output(""))
        assert result.score == 0.0
        assert result.metadata["reason"] == "missing"

    def test_none_intro_scores_zero(self):
        result = intro_quality(output={"introduction": None, "sections": []})
        assert result.score == 0.0

    def test_whitespace_only_scores_zero(self):
        result = intro_quality(output=_make_output("   "))
        assert result.score == 0.0


class TestIntroQualityTemplate:
    def test_template_fallback_scores_low(self):
        result = intro_quality(
            output=_make_output(
                "Here's your roundup of the latest in space technology.",
                _make_sections(),
            )
        )
        # Template detected → not_template = 0.0, and short intro
        assert result.score < 0.4
        assert result.metadata["not_template"] == 0.0

    def test_this_week_template_scores_low(self):
        result = intro_quality(
            output=_make_output(
                "This week in space: Starship, Neutron, Europa Clipper, and more.",
                _make_sections(),
            )
        )
        assert result.score < 0.5
        assert result.metadata["not_template"] == 0.0


class TestIntroQualityGeneric:
    def test_generic_intro_scores_medium(self):
        """An intro that's not a template but has no specific content references."""
        result = intro_quality(
            output=_make_output(
                "An exciting week for the space industry with several major "
                "developments across launch vehicles and planetary science. "
                "Multiple companies made progress on their next-generation rockets.",
                _make_sections(),
            )
        )
        # Not template, decent length, but low specificity/substance
        assert 0.3 < result.score < 0.7
        assert result.metadata["not_template"] == 1.0


class TestIntroQualitySubstantive:
    def test_substantive_intro_scores_high(self):
        """Intro with named entities, summary details, and engagement markers."""
        result = intro_quality(
            output=_make_output(
                "SpaceX's Starship achieved a historic milestone this week, completing "
                "its first stable orbital flight at 250 km altitude — a breakthrough "
                "that fundamentally changes the economics of heavy-lift launch. "
                "Meanwhile, Europa Clipper's radar soundings revealed subsurface "
                "liquid water beneath the Europan ice shell, and Rocket Lab's "
                "Neutron passed critical structural tests at Wallops Island. "
                "Is 2026 the year reusable heavy-lift finally delivers?",
                _make_sections(),
            )
        )
        assert result.score >= 0.8
        assert result.metadata["not_template"] == 1.0
        assert result.metadata["specificity_overlap"] >= 4
        assert result.metadata["substance_overlap"] >= 2
        assert result.metadata["engagement_signals"] >= 2

    def test_engagement_question_detected(self):
        result = intro_quality(
            output=_make_output(
                "What does the first orbital Starship flight mean for the "
                "future of space exploration? This week we explore that question.",
                _make_sections(),
            )
        )
        assert result.metadata["engagement_signals"] >= 1

    def test_engagement_numbers_detected(self):
        result = intro_quality(
            output=_make_output(
                "SpaceX's Starship reached 250 km altitude in its first orbital "
                "attempt, while Europa Clipper found water at 15 km depth.",
                _make_sections(),
            )
        )
        assert result.metadata["engagement_signals"] >= 1


class TestIntroQualityPresence:
    def test_very_short_intro_penalized(self):
        result = intro_quality(
            output=_make_output("Big week for space.", _make_sections())
        )
        assert result.metadata["presence"] < 0.5

    def test_moderate_length_scores_full_presence(self):
        # 40 words
        intro = " ".join(["word"] * 40)
        result = intro_quality(output=_make_output(intro))
        assert result.metadata["presence"] == 1.0
