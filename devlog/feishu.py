"""Optional Feishu uploader (shells out to lark-cli)."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from .config import FeishuConfig

log = logging.getLogger(__name__)


# Map free-text category labels (from "[xxx]" tags in checklist) to folder keys.
# Order matters: first match wins. Keep keys lowercase for case-insensitive match.
CATEGORY_TO_FOLDER_KEY: list[tuple[tuple[str, ...], str]] = [
    (("踩坑", "pit", "bug", "故障"), "pit"),
    (("工具", "tool", "tools"), "tool"),
    (("sop", "流程", "规范"), "sop"),
    (("决策", "decision", "选型"), "decision"),
    (("待办", "todo", "task"), "active"),
    (("知识", "library", "note"), "sop"),
]


class FeishuError(RuntimeError):
    pass


def resolve_folder_key(category: str) -> str | None:
    """Map a `[xxx]` category label to a folder-key in `feishu.folders`."""

    if not category:
        return None
    needle = category.strip().lower()
    for aliases, key in CATEGORY_TO_FOLDER_KEY:
        if needle in aliases:
            return key
    return None


def post_to_inbox(cfg: FeishuConfig, md_path: Path, title: str) -> str:
    """Create a Feishu docx in the configured Inbox folder. Returns the new doc URL."""

    if not cfg.enabled:
        raise FeishuError("feishu.enabled = false")
    if not cfg.inbox_folder_token:
        raise FeishuError("feishu.inbox_folder_token is empty")
    return _create_docx(cfg, md_path, title, cfg.inbox_folder_token)


def post_to_folder(cfg: FeishuConfig, md_path: Path, title: str, folder_token: str) -> str:
    """Create a Feishu docx in an arbitrary configured folder."""

    if not cfg.enabled:
        raise FeishuError("feishu.enabled = false")
    if not folder_token:
        raise FeishuError("folder_token is empty")
    return _create_docx(cfg, md_path, title, folder_token)


def _create_docx(cfg: FeishuConfig, md_path: Path, title: str, folder_token: str) -> str:
    if not shutil.which(cfg.lark_cli):
        raise FeishuError(f"lark-cli not found in PATH: {cfg.lark_cli}")
    if not md_path.exists():
        raise FeishuError(f"markdown not found: {md_path}")

    commands = [
        [
            cfg.lark_cli,
            "docs",
            "+create",
            "--title",
            title,
            "--folder-token",
            folder_token,
            "--markdown",
            f"@{md_path}",
        ],
        [
            cfg.lark_cli,
            "docs",
            "+create",
            "--api-version",
            "v2",
            "--doc-format",
            "markdown",
            "--title",
            title,
            "--folder-token",
            folder_token,
            "--content",
            f"@{md_path}",
        ],
    ]
    errors: list[str] = []
    for index, cmd in enumerate(commands):
        log.info("posting to feishu: %s", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            return _extract_doc_url(proc.stdout)

        error = (proc.stderr.strip() or proc.stdout.strip())[:500]
        if error:
            errors.append(error)
        if index == 0 and _should_try_legacy_create(proc.stderr, proc.stdout):
            continue
        break

    detail = "; ".join(errors) or "unknown error"
    raise FeishuError(f"lark-cli failed: {detail}")


def _should_try_legacy_create(stderr: str, stdout: str) -> bool:
    text = f"{stderr}\n{stdout}".lower()
    return (
        "unknown flag" in text
        or "flag provided but not defined" in text
        or ("usage:" in text and "--markdown" not in text)
    )


def _extract_doc_url(out: str) -> str:
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("http") and "docx" in line:
            return line
    return out.strip()
