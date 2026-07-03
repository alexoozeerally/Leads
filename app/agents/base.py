"""The ``AuditModule`` protocol every AI agent / analysis module implements.

A module takes an :class:`AuditContext` and returns an :class:`AuditResult`.
Defining this as a ``Protocol`` keeps the orchestration layer decoupled from any
concrete agent — services depend on the shape, not the class.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.schemas.audit import AuditResult
from app.schemas.context import AuditContext


@runtime_checkable
class AuditModule(Protocol):
    """Any object exposing ``async run(ctx) -> AuditResult``."""

    name: str

    async def run(self, ctx: AuditContext) -> AuditResult:  # pragma: no cover - protocol
        ...
