"""Unit tests for ``apex.pipeline.top_level_errors``."""

from __future__ import annotations

import httpx
import pytest

from apex.code_ground_truth.executor_client import ExecutionBackendError
from apex.pipeline import top_level_errors as te


def test_classify_value_error_is_validation() -> None:
    code, msg = te.classify_top_level_exception(ValueError("missing_test_solution_py"))
    assert code == te.APEX_VALIDATION
    assert "Validation failed" in msg


def test_classify_configuration_runtime_error() -> None:
    code, msg = te.classify_top_level_exception(
        RuntimeError("Missing Anthropic API key. Set ANTHROPIC_API_KEY or run: apex init")
    )
    assert code == te.APEX_CONFIGURATION
    assert "configuration" in msg.lower() or "apex init" in msg.lower()


def test_classify_runtime_error_with_httpx_cause_is_network() -> None:
    inner = httpx.HTTPError("inner")
    exc = RuntimeError("Anthropic completion failed")
    exc.__cause__ = inner
    code, msg = te.classify_top_level_exception(exc)
    assert code == te.APEX_NETWORK
    assert "network" in msg.lower()


def test_classify_execution_backend_error() -> None:
    code, msg = te.classify_top_level_exception(ExecutionBackendError("bad"))
    assert code == te.APEX_EXECUTION_BACKEND
    assert "execution backend" in msg.lower()


def test_build_metadata_omits_detail_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APEX_EXPOSE_ERROR_DETAILS", raising=False)
    meta = te.build_top_level_error_metadata(RuntimeError("secret https://x/y"))
    assert meta["error_code"] == te.APEX_INTERNAL
    assert "https://" not in meta["error"]
    assert "error_detail" not in meta


def test_build_metadata_includes_detail_when_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APEX_EXPOSE_ERROR_DETAILS", "1")
    meta = te.build_top_level_error_metadata(RuntimeError("secret https://x/y"))
    assert "error_detail" in meta
    assert "https://x/y" in meta["error_detail"]
