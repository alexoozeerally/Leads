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


def _parse_markers(user: str) -> dict[str, str]:
    """Extract MARKER: value lines from an email-generator prompt."""
    out: dict[str, str] = {}
    for line in user.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            if key.isupper() and value.strip():
                out[key] = value.strip()
    return out


def build_email_payload(user: str) -> dict:
    """A valid, honest :class:`OutreachContent` built from the prompt's markers.

    The deterministic offline stand-in uses exactly the compliment and two
    opportunities it was given — no invented claims — so tests and the demo
    exercise the real selection logic without a paid API call.
    """
    m = _parse_markers(user)
    business = m.get("BUSINESS", "your business")
    compliment = m.get("COMPLIMENT", "You clearly care about your customers.")
    opp1 = m.get("OPPORTUNITY_1", "A clearer homepage would help visitors act.")
    opp2 = m.get("OPPORTUNITY_2", "A mobile-friendly site would reach more customers.")
    cta = m.get("CALL_TO_ACTION", "Open to a quick chat?")

    unsubscribe = (
        "If you'd rather not hear from me, just reply 'unsubscribe' and I won't contact you again."
    )
    email_body = (
        f"Hi,\n\n{compliment}\n\n"
        f"I had a quick look at how {business} shows up online and spotted a couple of "
        f"things that could help:\n\n- {opp1}\n- {opp2}\n\n"
        f"{cta}\n\nBest wishes,\nAlex, Oozy Digital\n\n{unsubscribe}"
    )
    follow_up = (
        f"Hi again — just following up on my note about {business}'s website. "
        f"Happy to share a couple of quick ideas whenever suits.\n\n"
        f"Best,\nAlex, Oozy Digital\n\n{unsubscribe}"
    )
    linkedin = (
        f"Hi — I'm Alex from Oozy Digital. I help local businesses with their websites and "
        f"noticed a couple of small wins for {business}. Would you be open to a quick chat?"
    )
    return {
        "subject": f"A couple of quick ideas for {business}",
        "email_body": email_body,
        "follow_up": follow_up,
        "linkedin_message": linkedin,
        "compliment": compliment,
        "opportunities": [opp1, opp2],
        "call_to_action": cta,
        "_mock": True,
    }


def build_payload_for(system: str, user: str) -> dict | None:
    """Return an agent-appropriate mock payload based on the system prompt."""
    low = system.lower()
    if "first_impression" in low or "web-design director" in low:
        return build_vision_payload(user)
    if "outreach writer" in low or "call_to_action" in low:
        return build_email_payload(user)
    return None
