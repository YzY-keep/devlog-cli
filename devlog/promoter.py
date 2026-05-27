"""Promote checked items from a daily report to per-category Feishu folders.

The daily report is the single source of truth (Inbox-only writes).
When the human checks a `- [x] [category] body` line, `devlog promote`
turns each checked line into a standalone docx in the folder mapped from
its `[category]` tag via `feishu.folders` in config.toml.
"""

from __future__ import annotations

import contextlib
import logging
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .config import FeishuConfig
from .feishu import FeishuError, post_to_folder, resolve_folder_key

log = logging.getLogger(__name__)

# Only checked items (`- [x] ...`) are promoted. Unchecked items stay in Inbox.
_CHECKED_RE = re.compile(r"^-\s*\[x\]\s*(?:\[(?P<cat>[^\]]+)\]\s*)?(?P<body>.+)$", re.IGNORECASE)


@dataclass
class CheckedItem:
    category: str           # raw tag, e.g. "踩坑"
    body: str               # body text after the tag
    folder_key: str | None  # resolved key in cfg.folders, or None
    line_no: int            # 1-based line number in source report


@dataclass
class PromoteOutcome:
    item: CheckedItem
    folder_token: str | None = None
    url: str | None = None
    error: str | None = None
    skipped_reason: str | None = None  # "no_category" | "no_folder_mapping" | "no_folder_token"


@dataclass
class PromoteResult:
    report_path: Path
    items: list[CheckedItem] = field(default_factory=list)
    outcomes: list[PromoteOutcome] = field(default_factory=list)

    @property
    def succeeded(self) -> list[PromoteOutcome]:
        return [o for o in self.outcomes if o.url]

    @property
    def failed(self) -> list[PromoteOutcome]:
        return [o for o in self.outcomes if o.error]

    @property
    def skipped(self) -> list[PromoteOutcome]:
        return [o for o in self.outcomes if o.skipped_reason]


def parse_checked_items(md: str) -> list[CheckedItem]:
    """Extract every checked checkbox line from a Markdown report."""

    items: list[CheckedItem] = []
    for idx, raw in enumerate(md.splitlines(), start=1):
        m = _CHECKED_RE.match(raw.strip())
        if not m:
            continue
        cat = (m.group("cat") or "").strip()
        body = m.group("body").strip()
        if not body:
            continue
        folder_key = resolve_folder_key(cat) if cat else None
        items.append(
            CheckedItem(
                category=cat,
                body=body,
                folder_key=folder_key,
                line_no=idx,
            )
        )
    return items


def _build_item_doc(item: CheckedItem, report_path: Path) -> str:
    """Render a standalone docx body for one promoted item."""

    date_part = report_path.stem
    head = f"# [{item.category or 'note'}] {item.body}\n\n"
    meta = (
        f"> 来源: `{report_path.name}` 第 {item.line_no} 行  \n"
        f"> 分类: `{item.category or '(未分类)'}`  \n"
        f"> 日期: `{date_part}`\n\n"
    )
    body = f"## 详情\n\n{item.body}\n\n## 后续\n\n- [ ] 补充上下文/链接\n- [ ] 验证/归档\n"
    return head + meta + body


def _make_title(item: CheckedItem, report_path: Path) -> str:
    date_part = report_path.stem
    cat = item.category or "note"
    # Trim long bodies to keep doc title readable.
    snippet = item.body if len(item.body) <= 60 else item.body[:57] + "…"
    return f"[{cat}] {snippet} ({date_part})"


def promote(
    cfg: FeishuConfig,
    report_path: Path,
    *,
    dry_run: bool = False,
) -> PromoteResult:
    """Read a daily report, push each checked item to its mapped folder."""

    if not report_path.exists():
        raise FeishuError(f"report not found: {report_path}")

    md = report_path.read_text(encoding="utf-8")
    items = parse_checked_items(md)
    result = PromoteResult(report_path=report_path, items=items)

    for item in items:
        outcome = PromoteOutcome(item=item)

        if not item.category:
            outcome.skipped_reason = "no_category"
            result.outcomes.append(outcome)
            continue
        if not item.folder_key:
            outcome.skipped_reason = "no_folder_mapping"
            result.outcomes.append(outcome)
            continue

        folder_token = cfg.folders.get(item.folder_key)
        if not folder_token:
            outcome.skipped_reason = "no_folder_token"
            result.outcomes.append(outcome)
            continue
        outcome.folder_token = folder_token

        if dry_run:
            result.outcomes.append(outcome)
            continue

        # Write the per-item doc to a temp file and hand off to lark-cli.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(_build_item_doc(item, report_path))
            tmp_path = Path(tmp.name)

        try:
            url = post_to_folder(cfg, tmp_path, _make_title(item, report_path), folder_token)
            outcome.url = url
        except FeishuError as exc:
            outcome.error = str(exc)
        finally:
            with contextlib.suppress(OSError):
                tmp_path.unlink(missing_ok=True)

        result.outcomes.append(outcome)

    return result


def render_plan(result: PromoteResult) -> str:
    """Pretty-print a promote plan/result for terminal review."""

    if not result.items:
        return "no checked items found.\n"

    lines = [f"report: {result.report_path}", f"checked items: {len(result.items)}", ""]
    for i, outcome in enumerate(result.outcomes, start=1):
        item = outcome.item
        prefix = f"  {i:>2}. L{item.line_no} [{item.category or '?'}]"
        snippet = item.body if len(item.body) <= 80 else item.body[:77] + "…"
        if outcome.url:
            lines.append(f"{prefix} ✓ → {outcome.url}")
        elif outcome.error:
            lines.append(f"{prefix} ✗ {snippet}  ({outcome.error})")
        elif outcome.skipped_reason:
            reason = {
                "no_category": "无分类标签",
                "no_folder_mapping": "类别未映射到 folder_key",
                "no_folder_token": f"folder_key={item.folder_key} 未在 [feishu.folders] 配置",
            }.get(outcome.skipped_reason, outcome.skipped_reason)
            lines.append(f"{prefix} – {snippet}  (跳过: {reason})")
        else:
            target = f"→ {item.folder_key} ({outcome.folder_token[:8]}…)"
            lines.append(f"{prefix} {snippet}  {target}")
    lines.append("")
    return "\n".join(lines)
