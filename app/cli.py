"""Command-line entrypoint.

Usage:
    leadfinder run-sample            # ingest the bundled sample CSV end-to-end
    leadfinder discover <industry> --town <town> --postcode <pc>
"""

from __future__ import annotations

import argparse
import asyncio

from app.agents.auditor import WebsiteAuditor
from app.business_providers.factory import get_provider
from app.config.logging import get_logger
from app.config.settings import get_settings
from app.crawler.crawler import WebsiteCrawler
from app.schemas.business import DiscoveryQuery
from app.services.competitor import CompetitorService
from app.services.fixture_server import serve_distinct_sites
from app.services.pipeline import LeadPipeline

log = get_logger(__name__)


def _print_summary(result) -> None:
    print(
        f"\nProcessed {len(result.outcomes)} businesses "
        "(sorted by opportunity, highest first):\n"
    )
    for line in result.summary_lines():
        print(line)
    print("\nDone. Open the dashboard:  uv run streamlit run app/dashboard/streamlit_app.py")


async def _run(query: DiscoveryQuery, provider: str | None, force: bool = False) -> int:
    settings = get_settings()
    active_provider = get_provider(provider, settings)
    # Real leads get competitor analysis too: rivals are discovered via the same
    # provider and their live websites are audited directly (no URL rewriting).
    competitor_service = CompetitorService(
        provider=get_provider(provider, settings),
        crawler=WebsiteCrawler(settings),
        auditor=WebsiteAuditor(settings=settings, check_links=False),
    )
    pipeline = LeadPipeline(provider=active_provider, competitor_service=competitor_service)
    print(
        f"Running pipeline (provider={provider or settings.business_provider}, "
        f"anthropic={'live' if settings.anthropic_enabled else 'mock'}, force={force})...\n"
    )
    result = await pipeline.run(query, force=force)
    print(f"Audited {result.audited}, skipped {result.skipped} (fresh within re-audit window).")
    _print_summary(result)
    return 0


async def _schedule(query: DiscoveryQuery, provider: str | None, interval: int, runs: int) -> int:
    from app.services.scheduler import run_scheduled

    settings = get_settings()
    pipeline = LeadPipeline(provider=get_provider(provider, settings))
    print(f"Scheduling {runs} run(s) every {interval} min. Fresh leads are skipped each run.\n")
    results = await run_scheduled(pipeline, query, interval_minutes=interval, max_runs=runs)
    for i, r in enumerate(results, 1):
        print(f"Run {i}: audited {r.audited}, skipped {r.skipped}")
    return 0


async def _run_sample() -> int:
    """End-to-end demo: serve fixture sites locally and audit them for real."""
    settings = get_settings()
    # The demo serves fixtures over HTTPS with a throwaway self-signed cert, so
    # trust it (crawler, robots fetch, link checker) for this run only.
    settings.crawler_verify_tls = False
    provider = get_provider("csv", settings)
    query = DiscoveryQuery(industry="", limit=25)  # empty industry -> all rows
    businesses = await provider.search(query)

    # Each business with a website gets its own local host (distinct port), so
    # they stay distinct records — as real businesses on separate domains would.
    with_sites = [b for b in businesses if b.website]
    home_files = [b.website.lstrip("/") for b in with_sites]
    with (
        serve_distinct_sites(home_files) as base_urls,
        serve_distinct_sites(["modern.html"]) as (competitor_base,),
    ):
        for biz, base_url in zip(with_sites, base_urls, strict=True):
            biz.website = f"{base_url}/{biz.website.lstrip('/')}"

        # Competitor sites are discovered fresh from the CSV as bare filenames;
        # resolve them onto a shared fixture server so they can be audited too.
        def resolve(raw: str) -> str:
            return raw if raw.startswith("http") else f"{competitor_base}/{raw.lstrip('/')}"

        competitor_service = CompetitorService(
            provider=get_provider("csv", settings),
            crawler=WebsiteCrawler(settings),
            auditor=WebsiteAuditor(settings=settings, check_links=False),
            website_resolver=resolve,
        )
        print(
            f"Serving {len(with_sites)} fixture sites on localhost and running the "
            f"pipeline (anthropic={'live' if settings.anthropic_enabled else 'mock'})...\n"
        )
        pipeline = LeadPipeline(provider=provider, competitor_service=competitor_service)
        result = await pipeline.process_all(businesses)

    _print_summary(result)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="leadfinder", description="AI Web-Design Lead Finder")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run-sample", help="Ingest the bundled sample CSV end-to-end.")

    disc = sub.add_parser("discover", help="Discover + audit businesses for an industry.")
    disc.add_argument("industry")
    disc.add_argument("--town", default=None)
    disc.add_argument("--county", default=None)
    disc.add_argument("--postcode", default=None)
    disc.add_argument("--radius-km", type=float, default=5.0)
    disc.add_argument("--limit", type=int, default=25)
    disc.add_argument("--provider", default=None, help="csv | osm (default: configured)")
    disc.add_argument("--force", action="store_true", help="Re-audit even if fresh.")

    sched = sub.add_parser("schedule", help="Run discovery on a repeating interval.")
    sched.add_argument("industry")
    sched.add_argument("--town", default=None)
    sched.add_argument("--postcode", default=None)
    sched.add_argument("--provider", default=None)
    sched.add_argument("--interval-minutes", type=int, default=1440)
    sched.add_argument("--runs", type=int, default=1, help="Number of runs (default 1).")

    args = parser.parse_args()

    if args.command == "run-sample":
        raise SystemExit(asyncio.run(_run_sample()))

    if args.command == "discover":
        query = DiscoveryQuery(
            industry=args.industry,
            town=args.town,
            county=args.county,
            postcode=args.postcode,
            radius_km=args.radius_km,
            limit=args.limit,
        )
        raise SystemExit(asyncio.run(_run(query, provider=args.provider, force=args.force)))

    if args.command == "schedule":
        query = DiscoveryQuery(
            industry=args.industry, town=args.town, postcode=args.postcode, limit=50
        )
        raise SystemExit(
            asyncio.run(_schedule(query, args.provider, args.interval_minutes, args.runs))
        )


if __name__ == "__main__":
    main()
