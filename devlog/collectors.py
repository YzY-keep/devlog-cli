"""Source collectors: read transcripts from Claude Code, Codex, Cursor."""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterable, Iterator
from datetime import date, datetime, timezone
from pathlib import Path

from .config import SourceConfig
from .models import Message, ensure_utc

log = logging.getLogger(__name__)


def collect_all(sources: Iterable[SourceConfig], on: date) -> list[Message]:
    """Pull messages for `on` from every enabled source. Failures are isolated per source."""

    out: list[Message] = []
    for src in sources:
        if not src.enabled:
            continue
        try:
            out.extend(_collect_one(src, on))
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("source %s failed: %s", src.name, exc)
    out.sort(key=lambda m: m.timestamp)
    return out


def _collect_one(src: SourceConfig, on: date) -> list[Message]:
    path = Path(src.path)
    if not path.exists():
        log.debug("source path missing: %s", path)
        return []
    if src.kind == "jsonl":
        return list(_iter_jsonl_dir(src.name, path, on))
    if src.kind == "sqlite":
        return list(_iter_cursor_sqlite(src.name, path, on))
    log.warning("unknown source kind %s", src.kind)
    return []


def _iter_jsonl_dir(source_name: str, root: Path, on: date) -> Iterator[Message]:
    """Walk a directory of *.jsonl session files (Claude Code / Codex layout)."""

    files = [root] if root.is_file() and root.suffix == ".jsonl" else sorted(root.rglob("*.jsonl"))

    for fp in files:
        try:
            mtime = datetime.fromtimestamp(fp.stat().st_mtime, tz=timezone.utc).astimezone().date()
        except OSError:
            continue
        # Cheap pre-filter: skip files clearly older than target day.
        if mtime < on:
            continue
        session_id = fp.stem
        yield from _parse_jsonl(source_name, session_id, fp, on)


def _parse_jsonl(source_name: str, session_id: str, fp: Path, on: date) -> Iterator[Message]:
    try:
        text = fp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        ts = _extract_timestamp(obj)
        if ts.astimezone().date() != on:
            continue

        role, content = _extract_role_content(obj)
        if not content:
            continue

        yield Message(
            source=source_name,
            session_id=session_id,
            role=role,
            content=content,
            timestamp=ts,
            cwd=obj.get("cwd") or (obj.get("payload") or {}).get("cwd"),
            extra={"raw_type": obj.get("type") or obj.get("event")},
        )


def _extract_timestamp(obj: dict) -> datetime:
    for key in ("timestamp", "ts", "time", "created_at"):
        v = obj.get(key)
        if not v:
            continue
        try:
            if isinstance(v, (int, float)):
                return datetime.fromtimestamp(v, tz=timezone.utc)
            return ensure_utc(datetime.fromisoformat(str(v).replace("Z", "+00:00")))
        except (ValueError, OSError):
            continue
    return datetime.now(tz=timezone.utc)


def _extract_role_content(obj: dict) -> tuple[str, str]:
    """Best-effort extraction across known JSONL schemas."""

    # Claude Code: {"type": "user"|"assistant", "message": {"role": ..., "content": [...]}}
    msg = obj.get("message")
    if isinstance(msg, dict):
        role = msg.get("role") or obj.get("type") or "user"
        content = msg.get("content")
        return role, _flatten_content(content)

    # Codex: {"type": "user_input"|"agent_message", "payload": {"text": "..."}}
    payload = obj.get("payload")
    if isinstance(payload, dict):
        text = payload.get("text") or payload.get("content") or ""
        role = "user" if "user" in (obj.get("type") or "") else "assistant"
        return role, _flatten_content(text)

    # Fallback flat
    return obj.get("role", "user"), _flatten_content(obj.get("content") or obj.get("text"))


def _flatten_content(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif "content" in item:
                    parts.append(_flatten_content(item["content"]))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(p for p in parts if p).strip()
    return str(content).strip()


def _iter_cursor_sqlite(source_name: str, db_path: Path, on: date) -> Iterator[Message]:
    """Read Cursor's globalStorage state.vscdb (sqlite) in read-only/immutable mode."""

    uri = f"file:{db_path}?mode=ro&immutable=1"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        log.warning("cursor sqlite open failed: %s", exc)
        return
    try:
        cur = conn.cursor()
        try:
            cur.execute("SELECT key, value FROM ItemTable WHERE key LIKE '%chat%' OR key LIKE '%composer%'")
        except sqlite3.Error:
            return
        for key, value in cur.fetchall():
            yield from _parse_cursor_blob(source_name, str(key), value, on)
    finally:
        conn.close()


def _parse_cursor_blob(source_name: str, key: str, blob, on: date) -> Iterator[Message]:
    if blob is None:
        return
    try:
        text = blob if isinstance(blob, str) else blob.decode("utf-8", errors="replace")
    except AttributeError:
        text = str(blob)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return

    candidates: list[dict] = []
    if isinstance(obj, dict):
        for k in ("messages", "conversation", "history", "items"):
            v = obj.get(k)
            if isinstance(v, list):
                candidates.extend(x for x in v if isinstance(x, dict))
    elif isinstance(obj, list):
        candidates = [x for x in obj if isinstance(x, dict)]

    for item in candidates:
        ts = _extract_timestamp(item)
        if ts.astimezone().date() != on:
            continue
        role, content = _extract_role_content(item)
        if not content:
            continue
        yield Message(
            source=source_name,
            session_id=key,
            role=role,
            content=content,
            timestamp=ts,
            cwd=None,
            extra={"cursor_key": key},
        )
