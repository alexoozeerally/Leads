"""Phase-1 opportunity scoring.

A deliberately simple, transparent score (0–100) derived from the audit modules
available so far. Higher = better web-design prospect (weaker/absent site =
bigger opportunity). This is expanded into the full :class:`LeadScore` in Phase 5;
kept isolated here so that evolution doesn't ripple through the pipeline.
"""

from __future__ import annotations

from app.schemas.audit import AuditResult, WebsiteState

# Website states that are automatically high-opportunity (no real site to lose).
_HIGH_OPPORTUNITY_STATES = {
    WebsiteState.NO_SITE,
    WebsiteState.PARKED,
    WebsiteState.BROKEN,
    WebsiteState.UNDER_CONSTRUCTION,
    WebsiteState.REDIRECT_LOOP,
    WebsiteState.INVALID_SSL,
}

# Only the website-quality modules drive the opportunity score. GBP/social/
# competitor results are informational context (they feed the full LeadScore in
# Phase 5) and must not distort the "how weak is the website" signal.
QUALITY_MODULES = ("auditor", "vision")


def opportunity_from_results(state: WebsiteState, results: dict[str, AuditResult]) -> float:
    """Compute a 0–100 opportunity score.

    - No/broken/parked site -> automatic high opportunity (90).
    - Otherwise: opportunity is the inverse of overall website quality (from the
      auditor + vision modules), so a poor site scores high and a polished site
      scores low.
    """
    if state in _HIGH_OPPORTUNITY_STATES:
        return 90.0

    total_value = 0.0
    total_max = 0.0
    for name in QUALITY_MODULES:
        result = results.get(name)
        if result is None:
            continue
        value, mx = result.total()
        total_value += value
        total_max += mx

    if total_max == 0:
        return 50.0  # nothing measurable -> neutral

    quality_ratio = total_value / total_max  # 0..1, higher = better site
    return round((1.0 - quality_ratio) * 100.0, 1)
