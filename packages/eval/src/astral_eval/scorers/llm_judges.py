"""LLM-based newsletter quality scorers using A-D rubrics.

Primary path: Anthropic SDK (Claude Haiku) with optional Braintrust tracing.
All judges return ``None`` when no API key is available, letting the runner
skip them gracefully.
"""

from __future__ import annotations

import os
import re
from typing import Any

from astral_eval.scores import CHOICE_SCORES, Score

# Claude Haiku -- cheap, fast, different model family than generation (Sonnet)
# to avoid self-preference bias
_DEFAULT_MODEL = "claude-haiku-4-5-20250929"


def _has_api_key() -> str | None:
    """Return the available provider: 'anthropic', 'braintrust', or None."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("BRAINTRUST_API_KEY"):
        return "braintrust"
    return None


def _get_anthropic_client():
    """Build an Anthropic client, optionally wrapped with Braintrust tracing."""
    import anthropic

    client = anthropic.AsyncAnthropic()

    # Wrap with Braintrust for automatic trace logging when available
    if os.environ.get("BRAINTRUST_API_KEY"):
        try:
            from braintrust import wrap_anthropic

            client = wrap_anthropic(client)
        except ImportError:
            pass

    return client


async def _judge_with_anthropic(
    name: str,
    system: str,
    user_content: str,
    model: str = _DEFAULT_MODEL,
) -> Score | None:
    """Send a rubric prompt to Claude, extract A/B/C/D choice, return Score."""
    client = _get_anthropic_client()

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=128,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception:
        return None

    text = response.content[0].text if response.content else ""
    match = re.search(r"\b([ABCD])\b", text)
    if not match:
        return Score(
            name=name,
            score=0.0,
            metadata={"error": "no_choice_found", "raw": text[:200]},
        )

    choice = match.group(1)
    return Score(
        name=name,
        score=CHOICE_SCORES[choice],
        metadata={"choice": choice, "raw": text[:200]},
    )


# ---------------------------------------------------------------------------
# Rubric prompts
# ---------------------------------------------------------------------------

_EDITORIAL_QUALITY_SYSTEM = """\
You are evaluating a space technology newsletter for editorial quality.

Rate the newsletter on this rubric:
A - Strong editorial voice, varied sentence structure, no filler or padding, \
every paragraph adds value.
B - Competent writing with occasional filler; voice is present but uneven.
C - Mostly functional but reads like a summary dump; little editorial personality.
D - Poor writing quality, repetitive structure, or significant filler.

Respond with exactly one letter (A, B, C, or D) \
followed by a one-sentence justification."""

_COVERAGE_ADEQUACY_SYSTEM = """\
You are evaluating whether a space technology newsletter adequately covers \
the week's important stories.

You will receive the newsletter draft and a list of the top input articles. \
Rate coverage on this rubric:
A - All major stories covered; no significant omissions.
B - Most important stories present; one notable gap.
C - Several important stories missing; coverage feels incomplete.
D - Major gaps; the newsletter misses the week's biggest developments.

Respond with exactly one letter (A, B, C, or D) \
followed by a one-sentence justification."""

_READABILITY_FIT_SYSTEM = """\
You are evaluating a space technology newsletter for readability and \
audience fit (space-industry professionals and enthusiasts).

Rate on this rubric:
A - Pitch-perfect for the audience: technical enough to inform, accessible \
enough to scan quickly. Good use of jargon where appropriate.
B - Mostly appropriate; occasional passages too dense or too dumbed-down.
C - Inconsistent tone; mixes overly technical and overly casual sections.
D - Wrong level for the audience; either impenetrably dense or insultingly simple.

Respond with exactly one letter (A, B, C, or D) \
followed by a one-sentence justification."""

_LINK_QUALITY_SYSTEM = """\
You are evaluating the quality of links in a space technology newsletter.

Rate on this rubric:
A - Claims are sourced with inline links; anchor text is descriptive; \
primary sources preferred over aggregators.
B - Most claims sourced; some vague anchor text like "here" or "this article".
C - Sparse linking; several unsourced claims; or mostly aggregator links.
D - Few or no links; or links don't match the claims they annotate.

Respond with exactly one letter (A, B, C, or D) \
followed by a one-sentence justification."""

_COHERENCE_FLOW_SYSTEM = """\
You are evaluating the structural coherence of a space technology newsletter.

Rate on this rubric:
A - Sections flow logically; there is a clear narrative arc from top story \
through deep-dives to quick links. Transitions feel intentional.
B - Mostly coherent; one section feels out of place or a transition is abrupt.
C - Sections seem randomly ordered; no narrative thread connects them.
D - Disorganized; items within sections don't belong together.

Respond with exactly one letter (A, B, C, or D) \
followed by a one-sentence justification."""


# ---------------------------------------------------------------------------
# Public scorer functions
# ---------------------------------------------------------------------------


async def editorial_quality(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Score | None:
    """Judge editorial voice, sentence variety, and filler."""
    if not _has_api_key():
        return None
    markdown = output.get("markdown", "")
    return await _judge_with_anthropic(
        "editorial_quality",
        _EDITORIAL_QUALITY_SYSTEM,
        f"Newsletter:\n\n{markdown}",
    )


async def coverage_adequacy(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Score | None:
    """Judge whether the week's important stories are covered."""
    if not _has_api_key():
        return None
    markdown = output.get("markdown", "")

    # Build context from top input items
    input_summary = ""
    if input:
        top = input[:20]
        lines = [
            f"- {item.get('title', '?')} ({item.get('source_name', '?')})"
            for item in top
        ]
        input_summary = "\n".join(lines)

    user = f"Newsletter:\n\n{markdown}"
    if input_summary:
        user += f"\n\n---\nTop input articles this week:\n{input_summary}"

    return await _judge_with_anthropic(
        "coverage_adequacy",
        _COVERAGE_ADEQUACY_SYSTEM,
        user,
    )


async def readability_fit(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Score | None:
    """Judge readability for a space-professional audience."""
    if not _has_api_key():
        return None
    markdown = output.get("markdown", "")
    return await _judge_with_anthropic(
        "readability_fit",
        _READABILITY_FIT_SYSTEM,
        f"Newsletter:\n\n{markdown}",
    )


async def link_quality(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Score | None:
    """Judge link sourcing, anchor text, and primary-source preference."""
    if not _has_api_key():
        return None
    markdown = output.get("markdown", "")
    return await _judge_with_anthropic(
        "link_quality",
        _LINK_QUALITY_SYSTEM,
        f"Newsletter:\n\n{markdown}",
    )


async def coherence_flow(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Score | None:
    """Judge section ordering, narrative arc, and transitions."""
    if not _has_api_key():
        return None
    markdown = output.get("markdown", "")
    return await _judge_with_anthropic(
        "coherence_flow",
        _COHERENCE_FLOW_SYSTEM,
        f"Newsletter:\n\n{markdown}",
    )
