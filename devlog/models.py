"""Unified message model and basic utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any


@dataclass
class Message:
    """One user/assistant turn from any source."""

    source: str           # claude-code | codex | cursor | ...
    session_id: str       # opaque per-source session identifier
    role: str             # user | assistant | system
    content: str
    timestamp: datetime   # always tz-aware (UTC if unknown)
    cwd: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def local_date(self) -> date:
        return self.timestamp.astimezone().date()


def ensure_utc(ts: datetime | None) -> datetime:
    if ts is None:
        return datetime.now(tz=timezone.utc)
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)
