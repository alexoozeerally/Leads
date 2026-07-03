"""A portable JSON column type that works on both SQLite and Postgres.

Uses SQLAlchemy's ``JSON`` variant; falls back to text-encoded JSON so behaviour
is identical across backends.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


class JSONEncodedDict(TypeDecorator):
    """Stores a dict/list as JSON text; returns the decoded object."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return json.loads(value)
