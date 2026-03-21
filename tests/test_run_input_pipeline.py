from __future__ import annotations

import asyncio

import pytest

from apex.config.constants import MCP_MAX_PROMPT_CHARS
from apex.pipeline import run as pipeline_run
from apex.pipeline import run_execute


def test_apex_run_blocks_oversized_prompt_before_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_client() -> object:
        raise AssertionError("LLM client must not load for oversize prompt")

    monkeypatch.setattr(run_execute, "load_llm_client_from_env", _no_client)

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
