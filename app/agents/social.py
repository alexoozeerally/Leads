"""Social presence analyser — data-available-only.

Combines the social links the provider surfaced with any found on the crawled
website. Reports which networks are present and which are **Unknown** (absent
from the data we have — never fabricated). When no social data exists at all,
the module says so and contributes no scores.
"""

from __future__ import annotations

from urllib.parse import urlparse

from app.schemas.audit import AuditResult, ScoreEntry
from app.schemas.context import AuditContext

_MODULE = "social"

# Network -> host fragments that identify it.
_NETWORKS = {
    "facebook": ("facebook.com", "fb.com"),
    "instagram": ("instagram.com",),
    "twitter": ("twitter.com", "x.com"),
    "linkedin": ("linkedin.com",),
    "youtube": ("youtube.com", "youtu.be"),
    "tiktok": ("tiktok.com",),
}


class SocialAgent:
    """AuditModule assessing the business's social-media presence."""

    name = _MODULE

    async def run(self, ctx: AuditContext) -> AuditResult:
        found = self._collect_links(ctx)
        present = sorted(found)
        unknown = [n for n in _NETWORKS if n not in found]

        scores: dict[str, ScoreEntry] = {}
        if present:
            # Score reflects breadth of presence (up to 4 networks saturates).
            value = min(10.0, len(present) / 4 * 10)
            scores["presence"] = ScoreEntry(
                value=round(value, 2),
                max=10,
                explanation=f"Active social profiles found: {', '.join(present)}.",
            )

        available = bool(present)
        notes = self._summarise(available, present, unknown)
        return AuditResult(
            module=_MODULE,
            scores=scores,
            notes=notes,
            raw={
                "available": available,
                "present": present,
                "unknown": unknown,
                "links": {n: found[n] for n in present},
            },
        )

    @staticmethod
    def _collect_links(ctx: AuditContext) -> dict[str, str]:
        """Map network -> a representative URL, from provider data + the crawl."""
        candidates: list[str] = list(ctx.business.social_links.values())
        if ctx.crawl and ctx.crawl.links:
            candidates.extend(ctx.crawl.links)

        found: dict[str, str] = {}
        for url in candidates:
            host = urlparse(url).netloc.lower()
            for network, fragments in _NETWORKS.items():
                if network in found:
                    continue
                if any(frag in host for frag in fragments):
                    found[network] = url
        return found

    @staticmethod
    def _summarise(available: bool, present: list[str], unknown: list[str]) -> str:
        if not available:
            return "No social-media profiles found in the available data (unknown)."
        note = f"Social presence: {', '.join(present)}."
        if unknown:
            note += f" No profile found for (unknown): {', '.join(unknown)}."
        return note
