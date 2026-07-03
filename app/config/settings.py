"""Application settings, loaded from environment / .env via pydantic-settings.

No secrets are hardcoded. Every configurable value has a sensible default so the
app runs locally (SQLite, mock Anthropic client) with zero setup, and switches to
Postgres + the real Anthropic API purely through environment variables.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration object. Instantiate via :func:`get_settings`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---------------------------------------------------------
    app_name: str = "AI Web-Design Lead Finder"
    environment: str = Field(default="local", description="local | docker | prod")
    log_level: str = "INFO"
    log_json: bool = Field(default=False, description="Emit structured JSON logs.")

    # --- Database ------------------------------------------------------------
    # SQLite (aiosqlite) by default so the app runs with no external services.
    # docker-compose overrides this with an asyncpg Postgres URL.
    database_url: str = "sqlite+aiosqlite:///./leadfinder.db"
    db_echo: bool = False

    # --- Anthropic / AI ------------------------------------------------------
    # If no key is present, agents fall back to a deterministic mock client so
    # the whole pipeline (and the test suite) runs offline.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    anthropic_max_tokens: int = 2048
    agent_max_retries: int = 2

    # --- Business discovery --------------------------------------------------
    business_provider: str = Field(default="csv", description="Active provider: csv | osm")
    csv_provider_path: str = "tests/fixtures/sample_businesses.csv"
    overpass_url: str = "https://overpass-api.de/api/interpreter"

    # --- Crawler / compliance ------------------------------------------------
    crawler_user_agent: str = (
        "LeadFinderBot/0.1 (+https://example.com/leadfinderbot; UK web-design prospecting; "
        "respects robots.txt; contact: hello@example.com)"
    )
    crawler_rate_limit_per_host: float = Field(
        default=1.0, description="Max requests per second per host."
    )
    crawler_timeout_seconds: float = 30.0
    crawler_respect_robots: bool = True
    screenshot_dir: str = "./data/screenshots"

    # --- Pipeline / robustness ----------------------------------------------
    reaudit_after_days: int = Field(
        default=30, description="Skip re-auditing a lead audited within this window."
    )

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def anthropic_enabled(self) -> bool:
        """True when a real API key is configured; otherwise agents mock."""
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (one per process)."""
    return Settings()
