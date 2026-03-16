"""Reference-based LLM judges comparing generated newsletters against The Orbital Index.

These judges receive the OI issue text as ``expected`` via kwargs. When no
reference is available (2026 windows, or OI not fetched), they return None
so the runner silently skips them.

Uses the same ``_judge()`` routing as standard judges
(Braintrust proxy -> Anthropic fallback).
"""

from __future__ import annotations

from typing import Any

from astral_eval.scores import Score

from .llm_judges import _judge

# ---------------------------------------------------------------------------
# Rubric prompts
# ---------------------------------------------------------------------------

_TOPIC_OVERLAP_SYSTEM = """\
You are comparing two space technology newsletters covering the same week.

"Generated" is an AI-generated newsletter. "Reference" is The Orbital Index, \
a respected human-written space newsletter.

Assess how well the generated newsletter covers the same major stories \
as the reference.

Rate on this rubric:
A - Same major stories covered; well-aligned topic selection.
B - Most major topics overlap; one significant story in the reference is missing.
C - Partial overlap; several reference topics missing.
D - Minimal overlap; the newsletters cover different stories.

Respond with exactly one letter (A, B, C, or D) \
followed by a one-sentence justification."""

_EDITORIAL_DEPTH_SYSTEM = """\
You are comparing two space technology newsletters covering the same week.

"Generated" is an AI-generated newsletter. "Reference" is The Orbital Index, \
a respected human-written space newsletter.

Assess whether the generated newsletter's analysis and commentary matches \
the depth and insight of the reference.

Rate on this rubric:
A - Matches or exceeds the reference's depth; adds meaningful context.
B - Competent but shallower; the reference provides more nuance.
C - Noticeably superficial compared to the reference.
D - No analytical value; the reference is clearly superior.

Respond with exactly one letter (A, B, C, or D) \
followed by a one-sentence justification."""

_STRUCTURAL_SIMILARITY_SYSTEM = """\
You are comparing two space technology newsletters covering the same week.

"Generated" is an AI-generated newsletter. "Reference" is The Orbital Index, \
a respected human-written space newsletter.

Assess whether the generated newsletter has a similar format and \
presentation approach — section diversity, mix of deep dives and quick \
links, use of data/figures, etc.

Rate on this rubric:
A - Similar structural approach; comparable section diversity.
B - Reasonable but less varied than the reference.
C - Flat or monotonous compared to the reference.
D - Completely different structural philosophy.

Respond with exactly one letter (A, B, C, or D) \
followed by a one-sentence justification."""


# ---------------------------------------------------------------------------
# Public scorer functions
# ---------------------------------------------------------------------------


def _build_comparison_prompt(generated: str, reference: str) -> str:
    """Build the user prompt comparing generated vs reference newsletter."""
    return (
        f"Generated newsletter:\n\n{generated}\n\n"
        f"---\n\n"
        f"Reference (The Orbital Index):\n\n{reference}"
    )


async def topic_overlap(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Score | None:
    """Compare topic coverage against the corresponding OI issue."""
    expected = kwargs.get("expected")
    if not expected:
        return None

    markdown = output.get("markdown", "")
    user_content = _build_comparison_prompt(markdown, expected)
    return await _judge("oi_topic_overlap", _TOPIC_OVERLAP_SYSTEM, user_content)


async def editorial_depth_comparison(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Score | None:
    """Compare analytical depth against the corresponding OI issue."""
    expected = kwargs.get("expected")
    if not expected:
        return None

    markdown = output.get("markdown", "")
    user_content = _build_comparison_prompt(markdown, expected)
    return await _judge("oi_editorial_depth", _EDITORIAL_DEPTH_SYSTEM, user_content)


async def structural_similarity(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Score | None:
    """Compare structural approach against the corresponding OI issue."""
    expected = kwargs.get("expected")
    if not expected:
        return None

    markdown = output.get("markdown", "")
    user_content = _build_comparison_prompt(markdown, expected)
    return await _judge(
        "oi_structural_similarity", _STRUCTURAL_SIMILARITY_SYSTEM, user_content
    )
