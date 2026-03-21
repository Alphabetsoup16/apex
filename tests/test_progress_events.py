from __future__ import annotations

import asyncio
import json
import logging

import pytest

from apex.observability.progress_events import (
    PROGRESS_EVENT_SCHEMA,
    build_progress_payload,
    emit_progress,
    progress_log_enabled,
    progress_run_scope,
)
from apex.pipeline.step_support import REQUIRED, run_async_step


def test_progress_log_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APEX_PROGRESS_LOG", raising=False)
    assert progress_log_enabled() is False


@pytest.mark.parametrize(
    "value",
    ["1", "true", "TRUE", "on", "yes", "y"],
)
def test_progress_log_enabled_truthy(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("APEX_PROGRESS_LOG", value)
    assert progress_log_enabled() is True


def test_build_progress_payload_skips_none() -> None:
    p = build_progress_payload("run_start", run_id="r1", mode_inferred=None, x=1)
    assert p["kind"] == "run_start"
    assert p["run_id"] == "r1"
    assert p["schema"] == PROGRESS_EVENT_SCHEMA
    assert "mode_inferred" not in p
    assert p["x"] == 1
    assert "ts_ms" in p


def test_emit_progress_noop_when_disabled(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APEX_PROGRESS_LOG", raising=False)
    caplog.set_level(logging.INFO, logger="apex.progress")
    emit_progress("x", run_id="r")
    assert caplog.records == []


def test_emit_progress_json_line_when_enabled(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APEX_PROGRESS_LOG", "1")
    caplog.set_level(logging.INFO, logger="apex.progress")
    emit_progress("run_start", run_id="rid", mode_effective="text")
    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].getMessage())
    assert payload["schema"] == PROGRESS_EVENT_SCHEMA
    assert payload["kind"] == "run_start"
    assert payload["run_id"] == "rid"
    assert payload["mode_effective"] == "text"


def test_progress_run_scope_supplies_run_id(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APEX_PROGRESS_LOG", "1")
    caplog.set_level(logging.INFO, logger="apex.progress")
    with progress_run_scope("scoped"):
        emit_progress("client_ready")
    payload = json.loads(caplog.records[0].getMessage())
    assert payload["run_id"] == "scoped"


def test_run_async_step_emits_when_scoped(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APEX_PROGRESS_LOG", "1")
    caplog.set_level(logging.INFO, logger="apex.progress")

    async def work() -> dict:
        return {"ok": True}

    with progress_run_scope("run-z"):
        asyncio.run(run_async_step("ensemble", REQUIRED, work))

    kinds = [json.loads(r.getMessage())["kind"] for r in caplog.records]
    assert kinds == ["step_start", "step_end"]
    end = json.loads(caplog.records[-1].getMessage())
    assert end["step_id"] == "ensemble"
    assert end["ok"] is True
    assert end["duration_ms"] >= 0
