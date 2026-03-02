"""Pass 2: LLM-based category classification using Claude Haiku."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from astral_core import SpaceCategory, get_llm_client, load_prompt

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_CONCURRENT = 5

_CATEGORY_DESCRIPTIONS = {
    SpaceCategory.LAUNCH_VEHICLES: (
        "Rockets, launch vehicles, propulsion, reusability"
    ),
    SpaceCategory.SPACE_SCIENCE: ("Astronomy, astrophysics, exoplanets, telescopes"),
    SpaceCategory.COMMERCIAL_SPACE: ("Private space companies, funding, space economy"),
    SpaceCategory.LUNAR: ("Moon missions, Artemis, lunar exploration, cislunar"),
    SpaceCategory.MARS: "Mars missions, rovers, Mars colonization",
    SpaceCategory.EARTH_OBSERVATION: ("Remote sensing, weather satellites, climate"),
    SpaceCategory.POLICY: ("Space policy, regulation, budgets, legislation"),
    SpaceCategory.INTERNATIONAL: ("Non-US space agencies (ESA, JAXA, CNSA, ISRO)"),
    SpaceCategory.ISS_STATIONS: ("Space stations, ISS, Tiangong, microgravity"),
    SpaceCategory.DEFENSE_SPACE: ("Military space, Space Force, missile defense"),
    SpaceCategory.SATELLITE_COMMS: ("Satellite internet, Starlink, constellations"),
    SpaceCategory.DEEP_SPACE: ("Outer planets, interstellar, asteroids, comets"),
    SpaceCategory.OFF_TOPIC: (
        "Not about space — unrelated content, broken/empty text, social chatter"
    ),
}

_SYSTEM_PROMPT = """You are a space news classifier. Given a title and excerpt, \
return exactly ONE category from the list below. Return ONLY the category value \
(e.g. "launch_vehicles"), nothing else.

If the content is not about space, or the text is too broken/empty to classify, \
return "off_topic".

Categories:
"""
for _cat, _desc in _CATEGORY_DESCRIPTIONS.items():
    _SYSTEM_PROMPT += f"- {_cat.value}: {_desc}\n"

_FEW_SHOT = [
    {
        "role": "user",
        "content": (
            "Title: SpaceX Starship completes first orbital flight\n"
            "Excerpt: SpaceX's Starship rocket completed its first full "
            "orbital test flight today, marking a milestone for the "
            "company's next-generation launch vehicle."
        ),
    },
    {"role": "assistant", "content": "launch_vehicles"},
    {
        "role": "user",
        "content": (
            "Title: JWST discovers high-redshift galaxy challenging models\n"
            "Excerpt: The James Webb Space Telescope has identified a massive "
            "galaxy at redshift z=14.3, pushing back the timeline for galaxy "
            "formation and challenging current cosmological models."
        ),
    },
    {"role": "assistant", "content": "space_science"},
    {
        "role": "user",
        "content": (
            "Title: India's Chandrayaan-4 mission approved by cabinet\n"
            "Excerpt: The Indian government has approved ISRO's Chandrayaan-4 "
            "lunar sample return mission with a budget of $600 million, "
            "targeting a 2028 launch window."
        ),
    },
    {"role": "assistant", "content": "lunar"},
    {
        "role": "user",
        "content": (
            "Title: Great thread on xkcd comics\n"
            "Excerpt: Just saw the latest xkcd and it's hilarious. "
            "Randall really outdid himself with this one."
        ),
    },
    {"role": "assistant", "content": "off_topic"},
]


async def classify_with_llm(
    title: str, excerpt: str | None = None
) -> SpaceCategory | None:
    """Classify a single item using Claude Haiku.

    Returns None if the API key is not set, the model returns
    an invalid category, or the call fails.
    """
    client = get_llm_client()
    if client is None:
        return None

    user_content = f"Title: {title}"
    if excerpt:
        user_content += f"\nExcerpt: {excerpt[:500]}"

    messages: list[dict[str, str]] = [
        *_FEW_SHOT,
        {"role": "user", "content": user_content},
    ]

    try:
        system = load_prompt("category-classifier", _SYSTEM_PROMPT)
        resp = await client.messages.create(
            model=MODEL,
            max_tokens=50,
            system=system,
            messages=messages,
        )
        raw = resp.content[0].text.strip().lower()

        # Validate against known categories
        valid = {c.value for c in SpaceCategory}
        if raw in valid:
            return SpaceCategory(raw)
        logger.warning("LLM returned unknown category: %s", raw)
        return None
    except Exception:
        logger.warning("LLM classification failed for: %s", title[:80], exc_info=True)
        return None


async def classify_batch_with_llm(
    items: list[tuple[str, str | None]],
    on_progress: Callable[[], None] | None = None,
) -> list[SpaceCategory | None]:
    """Classify multiple items concurrently with a semaphore.

    Args:
        items: list of (title, excerpt) tuples
        on_progress: called after each item completes (for progress bars)

    Returns:
        list of SpaceCategory or None, in the same order as input
    """
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async def _classify(title: str, excerpt: str | None) -> SpaceCategory | None:
        async with sem:
            result = await classify_with_llm(title, excerpt)
            if on_progress:
                on_progress()
            return result

    tasks = [_classify(title, excerpt) for title, excerpt in items]
    return list(await asyncio.gather(*tasks))
