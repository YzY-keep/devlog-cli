"""Diff today's report against yesterday for human review."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_ITEM_RE = re.compile(r"^-\s*\[[ x]\]\s*(?:\[(?P<cat>[^\]]+)\]\s*)?(?P<body>.+)$")


@dataclass
class DiffResult:
    added: list[str]
    removed: list[str]
    unchanged: int

    def render(self) -> str:
        if not self.added and not self.removed:
            return ""
        lines = ["## 🆚 与昨日对比", ""]
        if self.added:
            lines.append("**新增**")
            lines.extend(f"- ✨ {item}" for item in self.added)
            lines.append("")
        if self.removed:
            lines.append("**消失**")
            lines.extend(f"- ✓ {item}" for item in self.removed)
            lines.append("")
        lines.append(f"(未变: {self.unchanged} 条)\n")
        return "\n".join(lines)


def diff_against(today_md: str, yesterday_path: Path | None) -> DiffResult:
    today_items = _extract_items(today_md)
    yesterday_items: set[str] = set()
    if yesterday_path and yesterday_path.exists():
        yesterday_items = _extract_items(yesterday_path.read_text(encoding="utf-8"))

    added = sorted(today_items - yesterday_items)
    removed = sorted(yesterday_items - today_items)
    unchanged = len(today_items & yesterday_items)
    return DiffResult(added=added, removed=removed, unchanged=unchanged)


def _extract_items(md: str) -> set[str]:
    out: set[str] = set()
    for line in md.splitlines():
        m = _ITEM_RE.match(line.strip())
        if not m:
            continue
        cat = (m.group("cat") or "").strip()
        body = m.group("body").strip()
        key = f"[{cat}] {body}" if cat else body
        out.add(key)
    return out
