# PRD — AI Web-Design Lead Finder (placeholder)

> Placeholder for the original `PRD.md`. The authoritative build plan is
> [`BUILD_PROMPT.md`](BUILD_PROMPT.md). The ten success criteria below are the
> definition-of-done the phases deliver against.

## Success criteria

1. Discovers UK businesses for a given industry + location via a pluggable
   provider (no Google Maps scraping).
2. Crawls each website politely (robots.txt, truthful UA, rate limits) and
   renders JS, capturing desktop + mobile screenshots.
3. Runs an AI vision analysis of the site's design quality with explanations.
4. Runs a full technical + visual website audit, scoring every category with a
   rationale, and handles no-site / broken / parked states explicitly.
5. Analyses Google Business Profile + social presence where data exists, and
   reports "unknown" cleanly when it does not.
6. Compares each lead against nearby same-industry competitors and surfaces
   concrete, personalised sales opportunities.
7. Aggregates everything into a lead score (need, urgency, budget, likelihood,
   ROI, project value, Hot/Warm/Cold) with per-deduction explanations.
8. Generates reviewable outreach drafts (email, follow-up, LinkedIn) — never
   sent automatically.
9. Runs on a schedule with de-duplication, re-audit windows, retries, caching,
   structured logging, and audit history/versioning.
10. Presents everything in a dashboard: search, filter, sort, screenshots, full
    reports, competitor comparison, draft review/approval, and CSV export.

## Non-goals

- Automatic sending of any outreach.
- Scraping sources whose terms prohibit it (e.g. Google Maps).
- Inventing data to fill gaps.
