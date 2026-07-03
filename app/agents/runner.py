"""Structured-output helper shared by every AI agent.

Calls the LLM, extracts the JSON object, and validates it against a Pydantic
model. On parse/validation failure it retries with a corrective instruction
(bounded), then fails loudly — it never silently returns junk.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, ValidationError

from app.agents.llm_client import ImageInput, LLMClient
from app.config.logging import get_logger
from app.config.settings import get_settings
from app.exceptions import AgentOutputError

log = get_logger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model response (handles code fences)."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = re.sub(r"^json\s*", "", stripped, flags=re.IGNORECASE)
    match = _JSON_BLOCK.search(stripped)
    if not match:
        raise ValueError("no JSON object found in response")
    return json.loads(match.group(0))


async def generate_structured[T: BaseModel](
    client: LLMClient,
    *,
    system: str,
    user: str,
    schema: type[T],
    images: list[ImageInput] | None = None,
    max_retries: int | None = None,
) -> T:
    """Return a validated ``schema`` instance from the LLM, retrying on bad output."""
    retries = get_settings().agent_max_retries if max_retries is None else max_retries
    attempt = 0
    last_error: str = ""
    prompt = user

    while attempt <= retries:
        raw = await client.complete_json(system=system, user=prompt, images=images)
        try:
            data = _extract_json(raw)
            return schema.model_validate(data)
        except (ValueError, json.JSONDecodeError, ValidationError) as exc:
            last_error = str(exc)
            log.warning("agent.output_invalid", attempt=attempt, error=last_error[:300])
            attempt += 1
            prompt = (
                f"{user}\n\nYour previous response could not be parsed/validated: "
                f"{last_error}\nReturn ONLY a single valid JSON object matching the "
                f"required schema, with no prose or code fences."
            )

    raise AgentOutputError(
        f"Agent output failed validation after {retries + 1} attempts: {last_error}"
    )
