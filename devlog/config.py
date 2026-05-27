"""Configuration loader.

Default config lives in ~/.devlog/config.toml. CLI flags override file values.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - py310 fallback
    import tomli as tomllib  # type: ignore[no-redef]


DEFAULT_CONFIG_DIR = Path.home() / ".devlog"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"
DEFAULT_OUTPUT_DIR = DEFAULT_CONFIG_DIR / "reports"
DEFAULT_STATE_DIR = DEFAULT_CONFIG_DIR / "state"


@dataclass
class SourceConfig:
    """One transcript source (claude / codex / cursor / custom)."""

    name: str
    kind: str  # "jsonl" | "sqlite"
    path: str
    enabled: bool = True


@dataclass
class BackendConfig:
    """LLM summarizer backend."""

    name: str  # codex | cursor | claude-code | none
    command: list[str] = field(default_factory=list)
    timeout_sec: int = 120


@dataclass
class FeishuConfig:
    """Feishu upload destination."""

    enabled: bool = False
    inbox_folder_token: str = ""
    lark_cli: str = "lark-cli"
    # Optional per-category folders used by `devlog promote`.
    # Keys are category labels matched against the `[xxx]` tag in checklist items.
    # Recommended keys: pit, tool, sop, decision, active, archive.
    folders: dict[str, str] = field(default_factory=dict)


@dataclass
class Config:
    sources: list[SourceConfig]
    backends: list[BackendConfig]  # try in order; first success wins
    feishu: FeishuConfig
    output_dir: Path = DEFAULT_OUTPUT_DIR
    state_dir: Path = DEFAULT_STATE_DIR
    max_messages_per_source: int = 500


def _default_sources() -> list[SourceConfig]:
    home = Path.home()
    return [
        SourceConfig(
            name="claude-code",
            kind="jsonl",
            path=str(home / ".claude" / "projects"),
        ),
        SourceConfig(
            name="codex",
            kind="jsonl",
            path=str(home / ".codex" / "sessions"),
        ),
        SourceConfig(
            name="cursor",
            kind="sqlite",
            path=str(
                home
                / "Library"
                / "Application Support"
                / "Cursor"
                / "User"
                / "globalStorage"
                / "state.vscdb"
            ),
        ),
    ]


def _default_backends() -> list[BackendConfig]:
    return [
        BackendConfig(name="codex", command=["codex", "exec", "--skip-git-repo-check", "-"]),
        BackendConfig(name="cursor", command=["cursor"]),  # opens prompt for manual run
        BackendConfig(name="none"),
    ]


def load_config(path: Path | None = None) -> Config:
    """Load config from TOML; fall back to built-in defaults."""

    cfg_path = path or DEFAULT_CONFIG_PATH
    raw: dict[str, Any] = {}
    if cfg_path.exists():
        with cfg_path.open("rb") as fh:
            raw = tomllib.load(fh)

    sources_raw = raw.get("sources")
    if sources_raw:
        sources = [
            SourceConfig(
                name=s["name"],
                kind=s["kind"],
                path=os.path.expanduser(s["path"]),
                enabled=s.get("enabled", True),
            )
            for s in sources_raw
        ]
    else:
        sources = _default_sources()

    backends_raw = raw.get("backends")
    if backends_raw:
        backends = [
            BackendConfig(
                name=b["name"],
                command=b.get("command", []),
                timeout_sec=b.get("timeout_sec", 120),
            )
            for b in backends_raw
        ]
    else:
        backends = _default_backends()

    feishu_raw = raw.get("feishu", {})
    folders_raw = feishu_raw.get("folders", {})
    if not isinstance(folders_raw, dict):
        folders_raw = {}
    feishu = FeishuConfig(
        enabled=feishu_raw.get("enabled", False),
        inbox_folder_token=feishu_raw.get("inbox_folder_token", ""),
        lark_cli=feishu_raw.get("lark_cli", "lark-cli"),
        folders={str(k): str(v) for k, v in folders_raw.items() if v},
    )

    output_dir = Path(os.path.expanduser(raw.get("output_dir", str(DEFAULT_OUTPUT_DIR))))
    state_dir = Path(os.path.expanduser(raw.get("state_dir", str(DEFAULT_STATE_DIR))))

    return Config(
        sources=sources,
        backends=backends,
        feishu=feishu,
        output_dir=output_dir,
        state_dir=state_dir,
        max_messages_per_source=raw.get("max_messages_per_source", 500),
    )


def init_config(path: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write a starter config.toml to disk."""

    cfg_path = path or DEFAULT_CONFIG_PATH
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    if cfg_path.exists() and not overwrite:
        return cfg_path

    sample = """# devlog config — edit paths to match your machine.
output_dir = "~/.devlog/reports"
state_dir  = "~/.devlog/state"
max_messages_per_source = 500

[[sources]]
name    = "claude-code"
kind    = "jsonl"
path    = "~/.claude/projects"
enabled = true

[[sources]]
name    = "codex"
kind    = "jsonl"
path    = "~/.codex/sessions"
enabled = true

[[sources]]
name    = "cursor"
kind    = "sqlite"
path    = "~/Library/Application Support/Cursor/User/globalStorage/state.vscdb"
enabled = true

# Summarizer backends — tried in order; first one that exits 0 wins.
[[backends]]
name        = "codex"
command     = ["codex", "exec", "--skip-git-repo-check", "-"]
timeout_sec = 120

[[backends]]
name    = "cursor"
command = ["cursor"]

[[backends]]
name = "none"   # fallback: just dump the prompt for manual summarization

[feishu]
enabled            = false
inbox_folder_token = ""
lark_cli           = "lark-cli"

# Optional: per-category folders used by `devlog promote`.
# Map the [xxx] tag inside checked items to a target folder token.
# Recommended keys: pit (踩坑), tool (工具), sop (SOP), decision (决策),
#                   active (10-Active), archive (90-Archive).
[feishu.folders]
# pit      = ""
# tool     = ""
# sop      = ""
# decision = ""
# active   = ""
# archive  = ""
"""
    cfg_path.write_text(sample, encoding="utf-8")
    return cfg_path
