from __future__ import annotations

import asyncio

import pytest

import apex.pipeline.run_context as run_context
from apex.config.constants import (
    MCP_MAX_FINDINGS_POLICY_ENTRY_CHARS,
    MCP_MAX_FINDINGS_POLICY_ITEMS,
    MCP_MAX_PROMPT_CHARS,
)
from apex.pipeline import run as pipeline_run
from apex.safety.run_input_limits import parse_findings_policy_overrides


def test_apex_run_blocks_oversized_prompt_before_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_client() -> object:
        raise AssertionError("LLM client must not load for oversize prompt")

    monkeypatch.setattr(run_context, "load_llm_client_from_env", _no_client)

    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="x" * (MCP_MAX_PROMPT_CHARS + 1),
            mode="text",
            ensemble_runs=2,
            max_tokens=64,
        )
    )
    assert result.verdict == "blocked"
    assert result.metadata.get("input_validation") is True


def test_parse_findings_policy_overrides_accepts_none() -> None:
    err, tt, ss = parse_findings_policy_overrides(None, None)
    assert err is None
    assert tt == () and ss == ()


def test_parse_findings_policy_overrides_strips_and_preserves_order() -> None:
    err, tt, ss = parse_findings_policy_overrides(["  a ", "b"], ["low", " info "])
    assert err is None
    assert tt == ("a", "b")
    assert ss == ("low", "info")


def test_parse_findings_policy_overrides_rejects_blank_entry() -> None:
    err, tt, ss = parse_findings_policy_overrides(["ok", "  "], None)
    assert err is not None
    assert "empty" in err
    assert tt == () and ss == ()


def test_parse_findings_policy_overrides_rejects_nul_and_long_entry() -> None:
    err1, _, _ = parse_findings_policy_overrides(["a\x00b"], None)
    assert err1 is not None and "NUL" in err1

    err2, _, _ = parse_findings_policy_overrides(
        ["x" * (MCP_MAX_FINDINGS_POLICY_ENTRY_CHARS + 1)], None
    )
    assert err2 is not None and "characters" in err2


def test_apex_run_blocks_oversized_findings_ignore_list(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_client() -> object:
        raise AssertionError("LLM client must not load when policy lists are invalid")

    monkeypatch.setattr(run_context, "load_llm_client_from_env", _no_client)

    bad = ["x"] * (MCP_MAX_FINDINGS_POLICY_ITEMS + 1)
    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="hello",
            mode="text",
            ensemble_runs=2,
            max_tokens=64,
            findings_ignore_types=bad,
        )
    )
    assert result.verdict == "blocked"
    assert result.metadata.get("input_validation") is True
    err = str(result.metadata.get("error") or "")
    assert "findings_ignore_types" in err
    assert str(MCP_MAX_FINDINGS_POLICY_ITEMS) in err
