"""Scheduled runs.

Runs the pipeline on a fixed interval. Each run honours the re-audit window, so
fresh leads are skipped and only stale ones are re-audited. Designed to be driven
either by this in-process loop or by an external scheduler (cron / systemd timer)
calling ``leadfinder discover`` — both routes share the same freshness policy.
"""

from __future__ import annotations

import asyncio

from app.config.logging import get_logger
from app.schemas.business import DiscoveryQuery
from app.services.pipeline import LeadPipeline, PipelineResult

log = get_logger(__name__)


async def run_once(pipeline: LeadPipeline, query: DiscoveryQuery) -> PipelineResult:
    result = await pipeline.run(query)
    log.info("scheduler.run_complete", audited=result.audited, skipped=result.skipped)
    return result


async def run_scheduled(
    pipeline: LeadPipeline,
    query: DiscoveryQuery,
    *,
    interval_minutes: int,
    max_runs: int | None = None,
) -> list[PipelineResult]:
    """Run the pipeline every ``interval_minutes``.

    ``max_runs`` bounds the number of iterations (mainly for testing / one-shot
    cron-style use); ``None`` runs indefinitely until cancelled.
    """
    results: list[PipelineResult] = []
    run = 0
    while max_runs is None or run < max_runs:
        run += 1
        log.info("scheduler.run_start", run=run)
        results.append(await run_once(pipeline, query))
        if max_runs is not None and run >= max_runs:
            break
        await asyncio.sleep(interval_minutes * 60)
    return results
