# AI Web-Design Lead Finder

A modular Python platform that discovers local (UK) businesses, audits their
online presence, scores them as web-design prospects, and drafts personalised
outreach **for human review before sending**.

> Status: built in phases. See [`PROGRESS.md`](PROGRESS.md) for what's live at
> each checkpoint. The product runs end-to-end on sample data from Phase 1 on.

## What it does

1. **Discover** businesses through a pluggable provider interface (CSV import,
   OpenStreetMap/Overpass — no paid keys required).
2. **Crawl** each website with a polite, `robots.txt`-respecting Playwright
   crawler that renders JS and captures desktop + mobile screenshots.
3. **Audit** the site with AI agents (vision, technical auditor, GBP, social,
   competitor) — every score carries a human-readable explanation.
4. **Score** each lead (opportunity, budget, project value, likelihood,
   Hot/Warm/Cold) with a per-deduction rationale and **no fabricated data**.
5. **Draft** personalised outreach (email, follow-up, LinkedIn) that a human
   reviews and approves in the dashboard. Nothing sends automatically.

## Tech stack

Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Pydantic v2 · Alembic ·
PostgreSQL · Playwright · httpx · BeautifulSoup · Anthropic SDK · Streamlit ·
Docker · Pytest.

## Quick start (local, no Docker)

```bash
uv venv --python 3.12
uv sync --extra dev
cp .env.example .env            # defaults use a local SQLite DB — no Postgres needed
uv run alembic upgrade head     # create tables
uv run uvicorn app.main:app --reload   # API on :8000, GET /health -> 200
```

Run the tests (fully offline — mocked Anthropic client, recorded HTML, SQLite):

```bash
uv run pytest -q
```

## Quick start (Docker — app + Postgres)

```bash
cp .env.example .env
docker compose -f docker/docker-compose.yml up --build
# API:        http://localhost:8000/health
# Dashboard:  http://localhost:8501
```

## Running the pipeline (from Phase 1 on)

```bash
# Ingest the bundled sample businesses end-to-end (discover -> crawl -> vision -> store)
uv run leadfinder run-sample
# or:  make run-sample
```

Then open the Streamlit dashboard:

```bash
uv run streamlit run app/dashboard/streamlit_app.py
```

## Configuration

All settings come from environment variables (see [`.env.example`](.env.example)),
loaded via `pydantic-settings`. No secrets are hardcoded. Key variables:

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Async SQLAlchemy URL. SQLite for local, Postgres for Docker. | `sqlite+aiosqlite:///./leadfinder.db` |
| `ANTHROPIC_API_KEY` | Real Anthropic API key. If unset, a deterministic mock client is used. | _(unset)_ |
| `ANTHROPIC_MODEL` | Model id for AI agents. | `claude-sonnet-5` |
| `BUSINESS_PROVIDER` | Active discovery provider (`csv`, `osm`). | `csv` |
| `CRAWLER_USER_AGENT` | Truthful identifying UA string for the crawler. | see `.env.example` |
| `CRAWLER_RATE_LIMIT_PER_HOST` | Max requests/sec per host. | `1.0` |

## Compliance & ethics (UK) — please read

This platform scrapes websites and drafts B2B cold outreach. It is built to be
used responsibly. If you run it, these obligations are yours:

- **Crawling.** The crawler respects `robots.txt`, sends a **truthful,
  identifying** User-Agent, rate-limits per host, and times out gracefully. It
  does not hammer sites.
- **Data-source terms.** Discovery is provider-abstracted **specifically so you
  never scrape Google Maps directly** (that violates Google's terms). Use OSM /
  Overpass (ODbL — attribute OpenStreetMap contributors), licensed APIs, or your
  own CSV. Each provider notes its licence/ToS in code.
- **GDPR / PECR.** Cold email here is **B2B only** and **requires human approval
  before sending** — the system only drafts. A do-not-contact / suppression list
  is maintained and checked, every template includes an unsubscribe mechanism,
  and a short "lawful basis" note is stored per contact.
- **Unknown is never invented.** Where evidence is absent, fields are `null` /
  "unknown" and any score deduction says so explicitly. No data is fabricated
  anywhere in the pipeline.

## Project layout

```
app/
  config/            settings (pydantic-settings, reads .env)
  schemas/           Pydantic contracts (Business, AuditResult, LeadScore, ...)
  database/          SQLAlchemy models, repositories, Alembic migrations
  business_providers/provider interface + CSV/OSM implementations
  crawler/           Playwright crawler
  agents/            AI agents (vision, auditor, gbp, social, competitor, scoring, email)
  services/          orchestration wiring providers -> crawler -> agents -> repos
  prompts/           all AI prompts as .md files, loaded at runtime
  api/               FastAPI routers (thin)
  dashboard/         Streamlit app
tests/               mirrors app/; fixtures/ holds recorded HTML + sample data
docker/              Dockerfile, docker-compose.yml
docs/                original spec files + build plan
```

## Licence

For evaluation. Respect the licences and terms of every data source you point it at.
