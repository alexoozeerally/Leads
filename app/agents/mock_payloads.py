"""Deterministic mock agent payloads for offline runs.

When no Anthropic key is configured, agents run against :class:`MockLLMClient`,
which uses these builders to return **schema-valid but clearly synthetic** JSON.
Scores are seeded from a hash of the prompt so they are stable and vary per
business, which makes the offline demo/dashboard look realistic without ever
calling a paid API. Nothing here is presented as real analysis — the stored
``raw`` payload is flagged so mock data is never mistaken for a live audit.
"""

from __future__ import annotations

import hashlib

from app.agents.vision import VISION_DIMENSIONS


def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest(), 16)


def _score_from(seed: int, offset: int, lo: int = 2, hi: int = 9) -> int:
    span = hi - lo + 1
    return lo + (seed // (offset + 1)) % span


def build_vision_payload(user: str) -> dict:
    """A stable, valid :class:`VisionAnalysis`-shaped dict seeded by the prompt."""
    seed = _seed(user)
    dimensions = {}
    for i, dim in enumerate(VISION_DIMENSIONS):
        s = _score_from(seed, i + 1)
        dimensions[dim] = {
            "score": s,
            "explanation": (
                f"[mock] {dim.replace('_', ' ')} scored {s}/10 from the screenshots "
                "(deterministic offline stand-in for a live vision assessment)."
            ),
        }
    first = _score_from(seed, 0)
    return {
        "first_impression": first,
        "estimated_site_age_years": 3 + (seed % 8),
        "dimensions": dimensions,
        "summary": (
            "[mock] Offline vision stand-in. Overall first impression "
            f"{first}/10. Biggest opportunity: modernise layout and strengthen the "
            "primary call-to-action. Replace with a live run for a real assessment."
        ),
        "_mock": True,
    }


def build_payload_for(system: str, user: str) -> dict | None:
    """Return an agent-appropriate mock payload based on the system prompt."""
    low = system.lower()
    if "first_impression" in low or "web-design director" in low:
        return build_vision_payload(user)
    return None
