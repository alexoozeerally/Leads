"""Typed custom exceptions used across the platform.

A small, explicit hierarchy so callers can catch precisely and logs stay
meaningful. Never raise bare ``Exception`` in application code.
"""

from __future__ import annotations


class LeadFinderError(Exception):
    """Base class for all application errors."""


class ConfigError(LeadFinderError):
    """Invalid or missing configuration."""


class ProviderError(LeadFinderError):
    """A business provider could not fulfil a request."""


class CrawlError(LeadFinderError):
    """The crawler failed to fetch or render a page."""


class AgentError(LeadFinderError):
    """An AI agent failed (network, or output that never validated)."""


class AgentOutputError(AgentError):
    """The agent's output could not be parsed/validated after retries."""


class RepositoryError(LeadFinderError):
    """A persistence operation failed."""
