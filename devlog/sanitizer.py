"""Sanitizer: strip secrets, long code blocks, env injections before sending to LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Message

# Regex blacklist (ordered: most specific first).
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("JWT",      re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("AWS_KEY",  re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GH_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("BEARER",   re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}\b")),
    ("OPENAI",   re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("PRIVKEY",  re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\s\S]+?-----END [^-]+-----")),
    ("PASSWORD", re.compile(r"(?i)(?:password|passwd|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*[\"']?(?!\[REDACTED)([^\s\"'\[\]]{6,})")),
]

# Whitelist: keep things that *look* like creds but are documented public tokens.
_WHITELIST = re.compile(r"whiteboard\s+token=")

# Codex injects a long environment preamble; trim it.
_CODEX_ENV_HEADER = re.compile(
    r"<environment_context>[\s\S]*?</environment_context>", re.IGNORECASE
)

_LONG_CODE_BLOCK = re.compile(r"```[\s\S]{800,}?```")


@dataclass
class SanitizeStats:
    redactions: dict[str, int]
    long_code_trimmed: int
    env_blocks_removed: int


def sanitize_messages(messages: list[Message]) -> tuple[list[Message], SanitizeStats]:
    stats = SanitizeStats(redactions={}, long_code_trimmed=0, env_blocks_removed=0)
    cleaned: list[Message] = []
    for m in messages:
        text, local_stats = sanitize_text(m.content)
        for k, v in local_stats.redactions.items():
            stats.redactions[k] = stats.redactions.get(k, 0) + v
        stats.long_code_trimmed += local_stats.long_code_trimmed
        stats.env_blocks_removed += local_stats.env_blocks_removed
        cleaned.append(
            Message(
                source=m.source,
                session_id=m.session_id,
                role=m.role,
                content=text,
                timestamp=m.timestamp,
                cwd=m.cwd,
                extra=m.extra,
            )
        )
    return cleaned, stats


def sanitize_text(text: str) -> tuple[str, SanitizeStats]:
    stats = SanitizeStats(redactions={}, long_code_trimmed=0, env_blocks_removed=0)
    if not text:
        return text, stats

    # Drop Codex env preambles wholesale.
    if _CODEX_ENV_HEADER.search(text):
        text = _CODEX_ENV_HEADER.sub("[ENV_CONTEXT_REMOVED]", text)
        stats.env_blocks_removed += 1

    # Trim oversized fenced code blocks.
    def _trim(match: re.Match[str]) -> str:
        stats.long_code_trimmed += 1
        body = match.group(0)
        head = body[:300]
        return head + "\n... [code block trimmed: " + str(len(body)) + " chars] ...\n```"

    text = _LONG_CODE_BLOCK.sub(_trim, text)

    # Redact secrets, respecting whitelist.
    def _redact(label: str):
        def _sub(match: re.Match[str]) -> str:
            if _WHITELIST.search(match.string[max(0, match.start() - 30): match.end()]):
                return match.group(0)
            stats.redactions[label] = stats.redactions.get(label, 0) + 1
            return f"[REDACTED:{label}]"
        return _sub

    for label, pat in _PATTERNS:
        text = pat.sub(_redact(label), text)

    return text, stats
