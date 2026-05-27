"""Pluggable summarizer backends. Tries each in order until one returns text."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import BackendConfig

log = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是一名工程助手,负责把当天的多端 AI 会话压缩成"开发日报"。
请只用提供的内容,**不要编造**未出现的事实。

输出严格 Markdown,章节顺序固定:
1. ## 🟢 今日新增
   每条一行,格式: - [ ] [类别] 一句话描述
   类别从 {踩坑, 工具, 决策, 待办, 知识} 中选
2. ## 🟡 状态变化
   只列那些"明显从 A → B"的事项,没有就写"无"
3. ## 🔴 待确认
   会话中出现但没有结论的问题
4. ## 📊 统计
   分 source 给出条数

规则:
- 每条 ≤ 50 字
- 引用具体命令/文件名/错误码时保留原文
- 不要输出任何解释性前后缀,直接给 Markdown
"""


@dataclass
class SummarizerResult:
    backend: str
    markdown: str
    raw_prompt_path: Path | None = None


class SummarizerError(RuntimeError):
    pass


def summarize(prompt: str, backends: list[BackendConfig], *, prompt_path: Path) -> SummarizerResult:
    """Try each backend in order. Always writes prompt to `prompt_path` first."""

    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    full_prompt = SYSTEM_PROMPT + "\n\n---\n\n" + prompt
    prompt_path.write_text(full_prompt, encoding="utf-8")

    last_err: Exception | None = None
    for backend in backends:
        if backend.name == "none":
            return SummarizerResult(
                backend="none",
                markdown=_placeholder_markdown(prompt_path),
                raw_prompt_path=prompt_path,
            )
        try:
            out = _run_backend(backend, full_prompt)
            if out.strip():
                return SummarizerResult(backend=backend.name, markdown=out, raw_prompt_path=prompt_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("backend %s failed: %s", backend.name, exc)
            last_err = exc
            continue
    if last_err:
        raise SummarizerError(f"all backends failed; last error: {last_err}")
    raise SummarizerError("no backends configured")


def _run_backend(backend: BackendConfig, prompt: str) -> str:
    if not backend.command:
        raise SummarizerError(f"backend {backend.name} has no command")
    proc = subprocess.run(
        backend.command,
        input=prompt,
        text=True,
        capture_output=True,
        timeout=backend.timeout_sec,
        check=False,
    )
    if proc.returncode != 0:
        raise SummarizerError(
            f"{backend.name} exit={proc.returncode}: {proc.stderr.strip()[:500]}"
        )
    return proc.stdout


def _placeholder_markdown(prompt_path: Path) -> str:
    return (
        "## 🟢 今日新增\n"
        f"- [ ] [待办] 未配置 LLM 后端,请人工总结 (prompt: `{prompt_path}`)\n\n"
        "## 🟡 状态变化\n无\n\n"
        "## 🔴 待确认\n无\n\n"
        "## 📊 统计\n见 prompt 文件\n"
    )
