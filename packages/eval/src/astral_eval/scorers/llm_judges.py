"""LLM-based newsletter quality scorers using A-D rubrics.

Primary path: Braintrust AI Proxy (GPT-4o-mini via OpenAI SDK) for cross-model
judging — avoids self-preference bias since Claude generates the drafts.
Fallback: Anthropic SDK (Claude Haiku) via ``astral_core.get_llm_client()``.
All judges return ``None`` when no API key is available, letting the runner
skip them gracefully.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

from astral_core import get_llm_client
from astral_eval.scores import CHOICE_SCORES, Score

logger = logging.getLogger(__name__)

# Fallback model when using direct Anthropic SDK
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Cross-model judge via Braintrust AI Proxy — different model family than
# the Sonnet drafter to avoid self-preference bias
_PROXY_MODEL = "gpt-4o-mini"


async def _judge_with_proxy(
    name: str,
    system: str,
    user_content: str,
) -> Score | None:
    """Judge via Braintrust AI Proxy using OpenAI SDK."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        return None

    api_key = os.environ.get("BRAINTRUST_API_KEY")
    if not api_key:
        return None

    client = AsyncOpenAI(
        base_url="https://api.braintrust.dev/v1/proxy",
        api_key=api_key,
    )

    try:
        response = await client.chat.completions.create(
            model=_PROXY_MODEL,
            max_tokens=128,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
        )
    except Exception:
        logger.warning("Braintrust proxy judge failed for %s", name, exc_info=True)
        return None

    text = response.choices[0].message.content or "" if response.choices else ""
    return _extract_score(name, text)


async def _judge_with_anthropic(
    name: str,
    system: str,
    user_content: str,
    model: str = _DEFAULT_MODEL,
) -> Score | None:
    """Send a rubric prompt to Claude, extract A/B/C/D choice, return Score."""
    client = get_llm_client()
    if client is None:
        return None

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=128,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception:
        logger.warning("Anthropic judge failed for %s", name, exc_info=True)
        return None

    text = response.content[0].text if response.content else ""
    return _extract_score(name, text)


def _extract_score(name: str, text: str) -> Score:
    """Parse A/B/C/D choice from judge response text."""
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


async def _judge(
    name: str,
    system: str,
    user_content: str,
) -> Score | None:
    """Route to Braintrust AI Proxy if available, else fall back to Anthropic."""
    if os.environ.get("BRAINTRUST_API_KEY"):
        result = await _judge_with_proxy(name, system, user_content)
        if result is not None:
            return result

    return await _judge_with_anthropic(name, system, user_content)


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
    markdown = output.get("markdown", "")
    return await _judge(
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

    return await _judge(
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
    markdown = output.get("markdown", "")
    return await _judge(
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
    markdown = output.get("markdown", "")
    return await _judge(
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
    markdown = output.get("markdown", "")
    return await _judge(
        "coherence_flow",
        _COHERENCE_FLOW_SYSTEM,
        f"Newsletter:\n\n{markdown}",
    )


# ---------------------------------------------------------------------------
# Thinking-mode ensemble judges
# ---------------------------------------------------------------------------

# Uses Claude Sonnet with extended thinking for deeper evaluation
_THINKING_MODEL = "claude-sonnet-4-20250514"


async def _judge_thinking(
    name: str,
    system: str,
    user_content: str,
    *,
    model: str | None = None,
) -> Score | None:
    """Judge via Anthropic SDK with extended thinking enabled."""
    client = get_llm_client()
    if client is None:
        return None

    try:
        response = await client.messages.create(
            model=model or _THINKING_MODEL,
            max_tokens=16000,
            thinking={"type": "enabled", "budget_tokens": 4096},
            # system param is not supported with thinking; prepend to user message
            messages=[
                {"role": "user", "content": f"{system}\n\n---\n\n{user_content}"}
            ],
        )
    except Exception:
        logger.warning("Thinking judge failed for %s", name, exc_info=True)
        return None

    # Extract text block (skip thinking blocks)
    text = next((b.text for b in response.content if b.type == "text"), "")
    return _extract_score(name, text)


async def _ensemble_judge(
    name: str,
    system: str,
    user_content: str,
    *,
    n: int = 3,
) -> Score | None:
    """Run N independent thinking-mode calls and return the median score."""
    tasks = [_judge_thinking(name, system, user_content) for _ in range(n)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    scores = [r for r in results if isinstance(r, Score) and r.score > 0]
    if not scores:
        return None
    scores.sort(key=lambda s: s.score)
    median = scores[len(scores) // 2]
    return Score(
        name=name,
        score=median.score,
        metadata={
            "choice": median.metadata.get("choice"),
            "ensemble_size": n,
            "all_scores": [s.score for s in scores],
            "all_choices": [s.metadata.get("choice") for s in scores],
            "aggregation": "median",
        },
    )


# ---------------------------------------------------------------------------
# Thinking-mode rubric prompts
# ---------------------------------------------------------------------------

_SUMMARY_FAITHFULNESS_SYSTEM = """\
You are evaluating a space technology newsletter for summary faithfulness.
Compare each item summary in the newsletter against the corresponding source \
article text provided below. Check for hallucinated claims, distortions, or \
unsupported inferences.

Rate on this rubric:
A - All summaries faithfully represent source content; no hallucinated claims.
B - Summaries are mostly faithful; one minor distortion or unsupported inference.
C - Several summaries misrepresent sources or add unsupported claims.
D - Widespread inaccuracy; summaries contradict or fabricate source content.

Respond with exactly one letter (A, B, C, or D) \
followed by a one-sentence justification."""

_SUMMARY_INFORMATIVENESS_SYSTEM = """\
You are evaluating a space technology newsletter for summary informativeness.
Assess whether each item summary adds value beyond the headline — specific \
facts, figures, implications, or context that a reader wouldn't get from \
scanning titles alone.

Rate on this rubric:
A - Every summary adds context beyond the headline — specific facts, figures, \
or implications.
B - Most summaries are informative; a few are just headline restatements.
C - Many summaries are shallow or repetitive; little value over scanning \
titles alone.
D - Summaries are mostly headline rewrites with padding words.

Respond with exactly one letter (A, B, C, or D) \
followed by a one-sentence justification."""

_INTRODUCTION_QUALITY_SYSTEM = """\
You are evaluating the introduction of a space technology newsletter.
Assess whether the opening is compelling, frames the issue's themes, and \
motivates the reader to continue.

Rate on this rubric:
A - Opening is engaging, frames the week's themes, and motivates reading \
further.
B - Competent intro that summarizes the issue but lacks a compelling hook.
C - Generic or templated intro; could apply to any week.
D - Missing, empty, or confusing introduction.

Respond with exactly one letter (A, B, C, or D) \
followed by a one-sentence justification."""

_TONE_CONSISTENCY_SYSTEM = """\
You are evaluating a space technology newsletter for tone consistency.
Assess whether the newsletter maintains a consistent editorial voice \
throughout all sections.

Rate on this rubric:
A - Uniform voice throughout; transitions between sections feel authored by \
one editor.
B - Mostly consistent; one section noticeably shifts register.
C - Uneven tone; alternates between formal and casual or between editorial \
styles.
D - Jarring shifts; reads like multiple authors stitched together.

Respond with exactly one letter (A, B, C, or D) \
followed by a one-sentence justification."""


# ---------------------------------------------------------------------------
# Public thinking-mode scorer functions
# ---------------------------------------------------------------------------


async def summary_faithfulness(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Score | None:
    """Judge whether summaries faithfully represent their source articles."""
    markdown = output.get("markdown", "")

    # Build source context from input items for cross-referencing
    source_context = ""
    if input:
        excerpts = []
        for item in input[:10]:
            title = item.get("title", "?")
            body = item.get("body_text") or item.get("excerpt") or ""
            body = body[:500]
            excerpts.append(f"- **{title}**: {body}")
        source_context = "\n".join(excerpts)

    user = f"Newsletter:\n\n{markdown}"
    if source_context:
        user += f"\n\n---\nSource articles:\n{source_context}"

    return await _ensemble_judge(
        "summary_faithfulness",
        _SUMMARY_FAITHFULNESS_SYSTEM,
        user,
    )


async def summary_informativeness(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Score | None:
    """Judge whether summaries add value beyond headlines."""
    markdown = output.get("markdown", "")
    return await _ensemble_judge(
        "summary_informativeness",
        _SUMMARY_INFORMATIVENESS_SYSTEM,
        f"Newsletter:\n\n{markdown}",
    )


async def introduction_quality(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Score | None:
    """Judge whether the introduction is compelling and frames the issue."""
    markdown = output.get("markdown", "")

    # Extract intro and section headings for context
    lines = markdown.split("\n")
    headings = [line for line in lines if line.startswith("## ")]
    heading_context = "\n".join(headings) if headings else ""

    introduction = output.get("introduction", "")
    user = f"Introduction:\n\n{introduction}"
    if heading_context:
        user += f"\n\n---\nSection headings:\n{heading_context}"

    return await _ensemble_judge(
        "introduction_quality",
        _INTRODUCTION_QUALITY_SYSTEM,
        user,
    )


async def tone_consistency(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Score | None:
    """Judge whether the newsletter maintains a consistent editorial voice."""
    markdown = output.get("markdown", "")
    return await _ensemble_judge(
        "tone_consistency",
        _TONE_CONSISTENCY_SYSTEM,
        f"Newsletter:\n\n{markdown}",
    )
