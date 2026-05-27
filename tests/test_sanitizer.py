from devlog.sanitizer import sanitize_text


def test_redacts_jwt():
    text = "token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dummy_signature_xx"
    cleaned, stats = sanitize_text(text)
    assert "[REDACTED:JWT]" in cleaned
    assert stats.redactions["JWT"] == 1


def test_redacts_openai_key():
    text = "OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz1234"
    cleaned, stats = sanitize_text(text)
    assert "[REDACTED:OPENAI]" in cleaned
    assert stats.redactions["OPENAI"] == 1


def test_whitelists_whiteboard_token():
    text = '<whiteboard token="abcdef1234567890abcdef" align="left"/>'
    cleaned, stats = sanitize_text(text)
    assert "abcdef1234567890abcdef" in cleaned
    assert stats.redactions == {}


def test_trims_long_code_block():
    body = "x" * 2000
    text = f"before\n```python\n{body}\n```\nafter"
    cleaned, stats = sanitize_text(text)
    assert stats.long_code_trimmed == 1
    assert "code block trimmed" in cleaned
    assert len(cleaned) < len(text)


def test_strips_codex_env_block():
    text = "ok\n<environment_context>secret env stuff</environment_context>\ndone"
    cleaned, stats = sanitize_text(text)
    assert stats.env_blocks_removed == 1
    assert "secret env stuff" not in cleaned
    assert "[ENV_CONTEXT_REMOVED]" in cleaned


def test_empty_input_safe():
    cleaned, stats = sanitize_text("")
    assert cleaned == ""
    assert stats.redactions == {}
