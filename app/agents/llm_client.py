"""LLM client abstraction.

Agents depend on the ``LLMClient`` protocol, never on the Anthropic SDK directly.
Two implementations:

- :class:`AnthropicClient` — calls the real Anthropic Messages API (vision-capable).
- :class:`MockLLMClient` — deterministic, offline; used in tests and whenever no
  API key is configured, so the whole pipeline runs with zero cost/network.

``complete_json`` asks the model to return a single JSON object; parsing +
validation happens in the agent runner.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.config.logging import get_logger
from app.config.settings import Settings, get_settings
from app.exceptions import AgentError

log = get_logger(__name__)


@dataclass
class ImageInput:
    """A screenshot to send to a vision model."""

    path: str
    label: str = "image"

    def as_base64(self) -> tuple[str, str]:
        data = Path(self.path).read_bytes()
        return base64.standard_b64encode(data).decode("ascii"), "image/png"


@runtime_checkable
class LLMClient(Protocol):
    async def complete_json(
        self, *, system: str, user: str, images: list[ImageInput] | None = None
    ) -> str:
        """Return the model's raw text response (expected to contain JSON)."""
        ...


class AnthropicClient:
    """Real Anthropic Messages API client (async)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        # Imported lazily so the package imports without the SDK/key present.
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=self._settings.anthropic_api_key)

    async def complete_json(
        self, *, system: str, user: str, images: list[ImageInput] | None = None
    ) -> str:
        content: list[dict] = []
        for img in images or []:
            b64, media = img.as_base64()
            content.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media, "data": b64},
                }
            )
        content.append({"type": "text", "text": user})

        try:
            resp = await self._create_with_retry(system, content)
        except Exception as exc:  # network / API errors after retries
            raise AgentError(f"Anthropic API call failed: {exc}") from exc

        parts = [block.text for block in resp.content if getattr(block, "type", "") == "text"]
        return "\n".join(parts)

    async def _create_with_retry(self, system: str, content: list[dict]):
        """Call the Messages API with bounded exponential-backoff retries."""
        from tenacity import (
            retry,
            stop_after_attempt,
            wait_exponential,
        )

        attempts = max(1, self._settings.anthropic_max_network_retries)

        @retry(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            reraise=True,
        )
        async def _call():
            return await self._client.messages.create(
                model=self._settings.anthropic_model,
                max_tokens=self._settings.anthropic_max_tokens,
                system=system,
                messages=[{"role": "user", "content": content}],
            )

        return await _call()


@dataclass
class MockLLMClient:
    """Deterministic offline client.

    Responses are seeded by a hash of the prompt so tests are stable, but the
    output shape mirrors what each agent expects. Register canned responses by
    system-prompt keyword via :attr:`responses`, else a generic JSON blob is
    returned.
    """

    responses: dict[str, dict] = field(default_factory=dict)
    calls: list[dict] = field(default_factory=list)

    async def complete_json(
        self, *, system: str, user: str, images: list[ImageInput] | None = None
    ) -> str:
        self.calls.append({"system": system, "user": user, "images": len(images or [])})
        for keyword, payload in self.responses.items():
            if keyword.lower() in system.lower():
                return json.dumps(payload)
        return json.dumps(self._default_payload(system, user))

    @staticmethod
    def _default_payload(system: str, user: str) -> dict:
        # Lazy import avoids a circular import (agents import this module).
        from app.agents.mock_payloads import build_payload_for

        payload = build_payload_for(system, user)
        if payload is not None:
            return payload
        seed = int(hashlib.sha256((system + user).encode()).hexdigest(), 16)
        return {"_mock": True, "_seed": seed % 1000}


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    """Return the active client, wrapped with caching + per-API rate limiting.

    Real Anthropic client when a key is configured, else the deterministic mock.
    """
    from app.agents.llm_cache import CachingRateLimitedClient

    settings = settings or get_settings()
    if settings.anthropic_enabled:
        log.info("llm.client", mode="anthropic", model=settings.anthropic_model)
        inner: LLMClient = AnthropicClient(settings)
    else:
        log.info("llm.client", mode="mock")
        inner = MockLLMClient()
    return CachingRateLimitedClient(inner, settings)
