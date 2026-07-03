"""Loads agent prompts from ``app/prompts/*.md`` at runtime.

Prompts are never inlined in code — they live as editable Markdown files so they
can be tuned without touching Python. Loaded prompts are cached per process.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.exceptions import ConfigError

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


@lru_cache
def load_prompt(name: str) -> str:
    """Return the text of ``app/prompts/<name>.md``."""
    path = _PROMPT_DIR / f"{name}.md"
    if not path.exists():
        raise ConfigError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")
