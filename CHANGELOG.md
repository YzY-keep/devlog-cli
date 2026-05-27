# Changelog

All notable changes will be documented here.

## [0.1.0] - 2026-05-26

### Added
- Initial CLI with `run / collect / post / init / version` subcommands
- Three built-in collectors: Claude Code JSONL, Codex JSONL, Cursor SQLite
- Sanitizer with 7-class regex blacklist + whitelist + Codex env stripping + long-code trimming
- Pluggable summarizer with `codex → cursor → none` fallback chain
- Day-over-day diff renderer (✨NEW / ✓removed)
- Optional Feishu Inbox uploader via `lark-cli`
- Smoke tests for sanitizer / differ / collector parsing
