"""One-time script to push hardcoded prompts to Braintrust as initial versions.

Uses the Braintrust REST API to create prompts, since the Python SDK only
supports loading/invoking prompts (creation is typically done via UI).

Run via: astral-eval seed-prompts
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BRAINTRUST_API = "https://api.braintrust.dev/v1"
_PROJECT = "astral-index"


def _collect_prompts() -> list[dict[str, Any]]:
    """Collect prompt definitions from their source modules."""
    from astral_author.draft import _INTRO_SYSTEM
    from astral_author.summarize import _ITEM_SYSTEM, _PROSE_SYSTEM
    from astral_ingest.classify.llm import _SYSTEM_PROMPT

    return [
        {
            "slug": "item-summarizer",
            "prompt_text": _ITEM_SYSTEM,
            "model": "claude-sonnet-4-20250514",
            "description": "Per-item summary prompt for the LLMSummarizer",
        },
        {
            "slug": "prose-generator",
            "prompt_text": _PROSE_SYSTEM,
            "model": "claude-sonnet-4-20250514",
            "description": "Editorial prose generation for deep-dive sections",
        },
        {
            "slug": "newsletter-intro",
            "prompt_text": _INTRO_SYSTEM,
            "model": "claude-sonnet-4-20250514",
            "description": "Newsletter introduction hook from top headlines",
        },
        {
            "slug": "category-classifier",
            "prompt_text": _SYSTEM_PROMPT,
            "model": "claude-haiku-4-5-20251001",
            "description": "Space news category classifier (LLM fallback pass)",
        },
    ]


def _get_or_create_project(client: httpx.Client) -> str:
    """Get the project ID, creating the project if needed."""
    resp = client.get(f"{_BRAINTRUST_API}/project", params={"project_name": _PROJECT})
    if resp.status_code == 200:
        data = resp.json()
        objects = data.get("objects", [])
        if objects:
            return objects[0]["id"]

    # Create the project
    resp = client.post(f"{_BRAINTRUST_API}/project", json={"name": _PROJECT})
    resp.raise_for_status()
    return resp.json()["id"]


def seed_prompts(*, dry_run: bool = False) -> list[str]:
    """Push current hardcoded prompts to Braintrust via REST API.

    Returns list of slugs that were seeded.
    """
    api_key = os.environ.get("BRAINTRUST_API_KEY")
    if not api_key:
        logger.warning(
            "BRAINTRUST_API_KEY not set — cannot seed prompts. "
            "Set this environment variable to push prompts to Braintrust."
        )
        raise SystemExit(1)

    prompts = _collect_prompts()

    if dry_run:
        return [p["slug"] for p in prompts]

    client = httpx.Client(
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )

    try:
        project_id = _get_or_create_project(client)

        seeded: list[str] = []
        for p in prompts:
            body = {
                "name": p["slug"],
                "slug": p["slug"],
                "project_id": project_id,
                "description": p["description"],
                "prompt_data": {
                    "prompt": {
                        "type": "chat",
                        "messages": [{"role": "system", "content": p["prompt_text"]}],
                    },
                    "options": {
                        "model": p["model"],
                    },
                },
            }

            resp = client.post(f"{_BRAINTRUST_API}/prompt", json=body)
            if resp.status_code == 409:
                logger.info("Prompt '%s' already exists, skipping", p["slug"])
            elif resp.is_success:
                logger.info("Created prompt '%s'", p["slug"])
            else:
                logger.warning(
                    "Failed to create prompt '%s': %s %s",
                    p["slug"],
                    resp.status_code,
                    resp.text[:200],
                )

            seeded.append(p["slug"])

        return seeded
    finally:
        client.close()
