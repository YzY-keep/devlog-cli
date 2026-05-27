"""Tests for the promote subcommand logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from devlog.config import FeishuConfig
from devlog.promoter import parse_checked_items, promote, render_plan

SAMPLE_REPORT = """# 2026-05-25 开发日报

## 🟢 今日新增
- [x] [踩坑] redis pipeline 在事务里不会聚合,要手动 multi
- [x] [工具] 发现 `uv run` 比 `pipx run` 启动快 5x
- [ ] [SOP] 整理代码评审清单
- [x] [决策] 选用 ruff 替换 black + isort
- [x] 没有分类的勾选项,会跳过
- [x] [未知类别] 这条会被分类标签匹配但 folder_key 解析不到
"""


def _write_report(tmp_path: Path) -> Path:
    p = tmp_path / "2026-05-25.md"
    p.write_text(SAMPLE_REPORT, encoding="utf-8")
    return p


def test_parse_checked_items_picks_only_checked():
    items = parse_checked_items(SAMPLE_REPORT)
    bodies = [i.body for i in items]
    assert any("redis pipeline" in b for b in bodies)
    assert any("uv run" in b for b in bodies)
    assert any("ruff" in b for b in bodies)
    # unchecked line skipped
    assert not any("代码评审清单" in b for b in bodies)
    # uncategorised checked line still parsed (handled by promote skip)
    assert any("没有分类的勾选项" in b for b in bodies)


def test_parse_resolves_known_categories():
    items = parse_checked_items(SAMPLE_REPORT)
    by_key = {i.body: i.folder_key for i in items}
    pit = next(b for b in by_key if "redis pipeline" in b)
    tool = next(b for b in by_key if "uv run" in b)
    dec = next(b for b in by_key if "ruff" in b)
    assert by_key[pit] == "pit"
    assert by_key[tool] == "tool"
    assert by_key[dec] == "decision"


def test_promote_dry_run_does_not_upload(tmp_path, monkeypatch):
    called = []

    def fake_post(cfg, md_path, title, folder_token):
        called.append((title, folder_token))
        return "https://example.com/docx/xxx"

    monkeypatch.setattr("devlog.promoter.post_to_folder", fake_post)

    cfg = FeishuConfig(
        enabled=True,
        inbox_folder_token="inbox",
        folders={"pit": "F_PIT", "tool": "F_TOOL", "decision": "F_DEC"},
    )
    report = _write_report(tmp_path)

    result = promote(cfg, report, dry_run=True)
    assert called == []
    # 3 actionable items have folder_token resolved
    resolved = [o for o in result.outcomes if o.folder_token]
    assert len(resolved) == 3


def test_promote_uploads_each_checked_item(tmp_path, monkeypatch):
    seen = []

    def fake_post(cfg, md_path, title, folder_token):
        seen.append((title, folder_token, Path(md_path).read_text(encoding="utf-8")))
        return f"https://example.com/docx/{folder_token}"

    monkeypatch.setattr("devlog.promoter.post_to_folder", fake_post)

    cfg = FeishuConfig(
        enabled=True,
        inbox_folder_token="inbox",
        folders={"pit": "F_PIT", "tool": "F_TOOL", "decision": "F_DEC"},
    )
    report = _write_report(tmp_path)
    result = promote(cfg, report, dry_run=False)

    assert len(seen) == 3
    titles = [t for t, _, _ in seen]
    assert any("[踩坑]" in t for t in titles)
    assert any("[工具]" in t for t in titles)
    assert any("[决策]" in t for t in titles)

    assert len(result.succeeded) == 3
    # uncategorised checked + unknown category checked → skipped
    assert len(result.skipped) == 2

    # Each per-item doc body references its source line.
    for _, _, body in seen:
        assert "来源:" in body
        assert "2026-05-25.md" in body


def test_promote_skip_when_folder_token_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "devlog.promoter.post_to_folder",
        lambda *a, **kw: pytest.fail("should not be called"),
    )
    cfg = FeishuConfig(enabled=True, inbox_folder_token="inbox", folders={})
    report = _write_report(tmp_path)
    result = promote(cfg, report, dry_run=False)
    assert result.succeeded == []
    # All actionable items skip with no_folder_token; uncategorised and unknown
    # category also skip but with different reasons.
    reasons = {o.skipped_reason for o in result.skipped}
    assert "no_folder_token" in reasons


def test_render_plan_handles_empty():
    cfg = FeishuConfig(enabled=True, inbox_folder_token="inbox")
    fake_report = Path("/nonexistent/empty.md")
    # Build a minimal result by calling parse on empty markdown.
    from devlog.promoter import PromoteResult

    result = PromoteResult(report_path=fake_report)
    assert "no checked items" in render_plan(result)
    assert cfg.enabled  # avoid unused warning
