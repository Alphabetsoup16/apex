from __future__ import annotations

from apex.config.constants import MCP_MAX_PROMPT_CHARS
from apex.mcp.input_guard import validate_correlation_id, validate_run_tool_inputs


def test_validate_correlation_id_accepts_alphanumeric() -> None:
    assert validate_correlation_id("abc-1._X") is None


def test_validate_correlation_id_rejects_bad_chars() -> None:
    assert validate_correlation_id("a/b") is not None
    assert validate_correlation_id("space id") is not None


def test_validate_correlation_id_none_or_blank() -> None:
    assert validate_correlation_id(None) is None
    assert validate_correlation_id("") is None
    assert validate_correlation_id("   ") is None


def test_validate_run_tool_rejects_nul() -> None:
    err = validate_run_tool_inputs(
        prompt="a\x00b",
        diff=None,
        repo_conventions=None,
        known_good_baseline=None,
        language=None,
        output_mode="candidate",
        supplementary_context=None,
    )
    assert err is not None
    assert "NUL" in err


def test_validate_run_tool_rejects_oversized_prompt() -> None:
    err = validate_run_tool_inputs(
        prompt="x" * (MCP_MAX_PROMPT_CHARS + 1),
        diff=None,
        repo_conventions=None,
        known_good_baseline=None,
        language=None,
        output_mode="candidate",
        supplementary_context=None,
    )
    assert err is not None
    assert "prompt" in err
