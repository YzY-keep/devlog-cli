from pathlib import Path
from types import SimpleNamespace

import pytest

from devlog.config import FeishuConfig
from devlog.feishu import FeishuError, post_to_inbox


def test_post_to_inbox_uses_markdown_flag(tmp_path, monkeypatch):
    md = tmp_path / "report.md"
    md.write_text("# report", encoding="utf-8")
    seen = []

    monkeypatch.setattr("devlog.feishu.shutil.which", lambda _: "/bin/lark-cli")

    def fake_run(cmd, capture_output, text, check):
        seen.append(cmd)
        return SimpleNamespace(returncode=0, stdout="https://example.com/docx/abc\n", stderr="")

    monkeypatch.setattr("devlog.feishu.subprocess.run", fake_run)

    cfg = FeishuConfig(enabled=True, inbox_folder_token="F_INBOX", lark_cli="lark-cli")
    assert post_to_inbox(cfg, md, "日报") == "https://example.com/docx/abc"
    assert seen == [
        [
            "lark-cli",
            "docs",
            "+create",
            "--title",
            "日报",
            "--folder-token",
            "F_INBOX",
            "--markdown",
            f"@{md}",
        ]
    ]


def test_post_to_inbox_falls_back_to_legacy_flags(tmp_path, monkeypatch):
    md = tmp_path / "report.md"
    md.write_text("# report", encoding="utf-8")
    seen = []

    monkeypatch.setattr("devlog.feishu.shutil.which", lambda _: "/bin/lark-cli")

    def fake_run(cmd, capture_output, text, check):
        seen.append(cmd)
        if "--markdown" in cmd:
            return SimpleNamespace(returncode=1, stdout="", stderr="unknown flag: --markdown")
        return SimpleNamespace(returncode=0, stdout="https://example.com/docx/legacy\n", stderr="")

    monkeypatch.setattr("devlog.feishu.subprocess.run", fake_run)

    cfg = FeishuConfig(enabled=True, inbox_folder_token="F_INBOX", lark_cli="lark-cli")
    assert post_to_inbox(cfg, md, "日报") == "https://example.com/docx/legacy"
    assert len(seen) == 2
    assert "--markdown" in seen[0]
    assert "--content" in seen[1]
    assert "--doc-format" in seen[1]


def test_post_to_inbox_reports_lark_cli_failure(tmp_path, monkeypatch):
    md = tmp_path / "report.md"
    md.write_text("# report", encoding="utf-8")

    monkeypatch.setattr("devlog.feishu.shutil.which", lambda _: "/bin/lark-cli")
    monkeypatch.setattr(
        "devlog.feishu.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="auth failed"),
    )

    cfg = FeishuConfig(enabled=True, inbox_folder_token="F_INBOX", lark_cli="lark-cli")
    with pytest.raises(FeishuError, match="auth failed"):
        post_to_inbox(cfg, md, "日报")
