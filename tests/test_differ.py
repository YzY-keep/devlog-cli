from pathlib import Path

from devlog.differ import diff_against


def test_added_and_removed(tmp_path: Path):
    yesterday = tmp_path / "y.md"
    yesterday.write_text(
        "## 🟢 今日新增\n- [ ] [踩坑] A\n- [ ] [工具] B\n",
        encoding="utf-8",
    )
    today = "## 🟢 今日新增\n- [ ] [踩坑] A\n- [ ] [决策] C\n"
    diff = diff_against(today, yesterday)
    assert diff.added == ["[决策] C"]
    assert diff.removed == ["[工具] B"]
    assert diff.unchanged == 1


def test_no_yesterday(tmp_path: Path):
    today = "- [ ] [踩坑] A\n"
    diff = diff_against(today, tmp_path / "missing.md")
    assert diff.added == ["[踩坑] A"]
    assert diff.removed == []


def test_render_empty():
    today = "- [ ] [踩坑] A"
    diff = diff_against(today, None)
    md = diff.render()
    assert "新增" in md
    assert "✨" in md
