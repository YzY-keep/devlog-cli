import json
from datetime import date, datetime, timezone
from pathlib import Path

from devlog.collectors import collect_all
from devlog.config import SourceConfig


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")


def test_claude_jsonl_collected(tmp_path: Path):
    today = date.today()
    ts = datetime.now(tz=timezone.utc).isoformat()
    session = tmp_path / "session.jsonl"
    _write_jsonl(session, [
        {"type": "user", "timestamp": ts,
         "message": {"role": "user", "content": "hello"},
         "cwd": "/repo"},
        {"type": "assistant", "timestamp": ts,
         "message": {"role": "assistant",
                     "content": [{"type": "text", "text": "world"}]}},
        # Stale (yesterday) — should be filtered.
        {"type": "user", "timestamp": "2020-01-01T00:00:00+00:00",
         "message": {"role": "user", "content": "stale"}},
    ])

    src = SourceConfig(name="claude-code", kind="jsonl", path=str(tmp_path))
    msgs = collect_all([src], today)
    contents = [m.content for m in msgs]
    assert "hello" in contents
    assert "world" in contents
    assert "stale" not in contents


def test_disabled_source_skipped(tmp_path: Path):
    src = SourceConfig(name="x", kind="jsonl", path=str(tmp_path), enabled=False)
    assert collect_all([src], date.today()) == []


def test_missing_path_isolated():
    src = SourceConfig(name="x", kind="jsonl", path="/no/such/path/zzz")
    assert collect_all([src], date.today()) == []
