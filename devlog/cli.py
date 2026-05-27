"""CLI entry point.

Subcommands:
- run     : collect → sanitize → summarize → write report (default)
- init    : write a starter config.toml
- collect : dump sanitized prompt only (no LLM call)
- post    : push an existing report Markdown to Feishu Inbox
- version : print version
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from . import __version__
from .collectors import collect_all
from .config import (
    Config,
    init_config,
    load_config,
)
from .differ import diff_against
from .feishu import FeishuError, post_to_inbox
from .promoter import promote, render_plan
from .report import build_prompt, build_report, build_stats
from .sanitizer import sanitize_messages
from .summarizer import SummarizerError, summarize


def _parse_date(s: str | None) -> date:
    if not s:
        return date.today()
    if s.lower() == "today":
        return date.today()
    if s.lower() == "yesterday":
        return date.today() - timedelta(days=1)
    return datetime.strptime(s, "%Y-%m-%d").date()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="devlog", description="Local AI session daily report.")
    p.add_argument("--config", type=Path, default=None, help="path to config.toml")
    p.add_argument("-v", "--verbose", action="count", default=0)
    sub = p.add_subparsers(dest="cmd")

    sp_run = sub.add_parser("run", help="generate today's report (default)")
    sp_run.add_argument("--date", default="today", help="YYYY-MM-DD | today | yesterday")
    sp_run.add_argument("--out", type=Path, default=None, help="output Markdown path")
    sp_run.add_argument("--no-llm", action="store_true", help="skip summarizer; emit prompt only")
    sp_run.add_argument("--no-diff", action="store_true", help="skip diff with yesterday")
    sp_run.add_argument("--post", action="store_true", help="also post to Feishu Inbox")

    sp_init = sub.add_parser("init", help="write starter config.toml")
    sp_init.add_argument("--force", action="store_true")

    sp_collect = sub.add_parser("collect", help="dump sanitized prompt without LLM call")
    sp_collect.add_argument("--date", default="today")
    sp_collect.add_argument("--out", type=Path, default=None)

    sp_post = sub.add_parser("post", help="post existing report to Feishu")
    sp_post.add_argument("file", type=Path)
    sp_post.add_argument("--title", default=None)

    sp_promote = sub.add_parser(
        "promote",
        help="promote [x] checked items in a report to per-category Feishu folders",
    )
    sp_promote.add_argument("--date", default="yesterday", help="YYYY-MM-DD | today | yesterday")
    sp_promote.add_argument("--file", type=Path, default=None, help="explicit report path")
    sp_promote.add_argument("--dry-run", action="store_true", help="show plan without uploading")
    sp_promote.add_argument("--yes", action="store_true", help="skip y/n confirmation")

    sub.add_parser("version", help="print version")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    cmd = args.cmd or "run"
    if cmd == "version":
        print(__version__)
        return 0
    if cmd == "init":
        path = init_config(args.config, overwrite=args.force)
        print(f"config written: {path}")
        return 0

    cfg = load_config(args.config)

    if cmd == "collect":
        return _cmd_collect(cfg, args)
    if cmd == "post":
        return _cmd_post(cfg, args)
    if cmd == "promote":
        return _cmd_promote(cfg, args)
    return _cmd_run(cfg, args)


def _cmd_collect(cfg: Config, args) -> int:
    on = _parse_date(args.date)
    msgs = collect_all(cfg.sources, on)
    cleaned, _ = sanitize_messages(msgs)
    prompt = build_prompt(cleaned, on)
    out = args.out or (cfg.output_dir / f"{on}-prompt.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(prompt, encoding="utf-8")
    print(f"wrote prompt ({len(cleaned)} messages) → {out}")
    return 0


def _cmd_post(cfg: Config, args) -> int:
    if not cfg.feishu.enabled:
        print("error: feishu.enabled = false in config", file=sys.stderr)
        return 2
    title = args.title or args.file.stem
    try:
        url = post_to_inbox(cfg.feishu, args.file, title)
    except FeishuError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(url)
    return 0


def _cmd_run(cfg: Config, args) -> int:
    on = _parse_date(args.date)
    msgs = collect_all(cfg.sources, on)
    if not msgs:
        print(f"no messages found for {on}", file=sys.stderr)
        return 1

    cleaned, sstats = sanitize_messages(msgs)
    prompt = build_prompt(cleaned, on)
    stats_md = build_stats(cleaned, sstats)

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = cfg.output_dir / f"{on}-prompt.md"

    if args.no_llm:
        prompt_path.write_text(prompt, encoding="utf-8")
        summary_md = "## 🟢 今日新增\n(LLM 已跳过,请人工填写)\n"
        backend = "skipped"
    else:
        try:
            res = summarize(prompt, cfg.backends, prompt_path=prompt_path)
            summary_md, backend = res.markdown, res.backend
        except SummarizerError as exc:
            print(f"summarizer error: {exc}", file=sys.stderr)
            return 2

    diff_md = ""
    if not args.no_diff:
        prev = cfg.output_dir / f"{on - timedelta(days=1)}.md"
        diff_md = diff_against(summary_md, prev).render()

    report = build_report(on, summary_md, stats_md, diff_md, backend)
    out = args.out or (cfg.output_dir / f"{on}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"wrote report → {out}")
    print(f"backend: {backend}  |  messages: {len(cleaned)}")

    if args.post:
        try:
            url = post_to_inbox(cfg.feishu, out, f"{on} 开发日报")
            print(f"feishu: {url}")
        except FeishuError as exc:
            print(f"feishu post failed: {exc}", file=sys.stderr)
            return 3
    return 0


def _cmd_promote(cfg: Config, args) -> int:
    if not cfg.feishu.enabled:
        print("error: feishu.enabled = false in config", file=sys.stderr)
        return 2

    if args.file:
        report_path = args.file
    else:
        on = _parse_date(args.date)
        report_path = cfg.output_dir / f"{on}.md"

    if not report_path.exists():
        print(f"error: report not found: {report_path}", file=sys.stderr)
        return 2

    # Phase 1: always print the plan first (dry-run).
    try:
        plan = promote(cfg.feishu, report_path, dry_run=True)
    except FeishuError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(render_plan(plan))

    if args.dry_run:
        return 0
    if not plan.items:
        return 0

    # Anything actionable? (has folder_token resolved)
    actionable = [o for o in plan.outcomes if o.folder_token and not o.skipped_reason]
    if not actionable:
        print("nothing to promote (all items skipped).", file=sys.stderr)
        return 0

    if not args.yes:
        try:
            reply = input(f"promote {len(actionable)} item(s) to Feishu? [y/N] ").strip().lower()
        except EOFError:
            reply = ""
        if reply not in ("y", "yes"):
            print("aborted.")
            return 0

    # Phase 2: actually upload.
    try:
        result = promote(cfg.feishu, report_path, dry_run=False)
    except FeishuError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(render_plan(result))
    print(
        f"done: {len(result.succeeded)} ok, "
        f"{len(result.failed)} failed, "
        f"{len(result.skipped)} skipped"
    )
    return 0 if not result.failed else 3


if __name__ == "__main__":
    sys.exit(main())
