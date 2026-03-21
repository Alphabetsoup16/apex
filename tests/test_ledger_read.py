from __future__ import annotations

import asyncio
import json

import pytest

from apex.ledger import read_ledger_snapshot, record_apex_run_to_ledger_if_enabled
from apex.models import ApexRunToolResult
from apex.pipeline.observability import finalize_run_result


def test_read_ledger_clamps_bad_limit(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("APEX_LEDGER_DISABLED", raising=False)
    missing = tmp_path / "nope.sqlite3"
    monkeypatch.setenv("APEX_LEDGER_PATH", str(missing))
    snap = read_ledger_snapshot(limit="not-an-int")  # type: ignore[arg-type]
    assert snap["schema"] == "apex.ledger.query/v1"
    assert "not found" in (snap.get("detail") or "").lower()


def test_read_ledger_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APEX_LEDGER_DISABLED", "1")
    monkeypatch.delenv("APEX_LEDGER_PATH", raising=False)
    snap = read_ledger_snapshot(limit=10)
    assert snap["schema"] == "apex.ledger.query/v1"
    assert snap["ledger_enabled"] is False
    assert snap["runs"] == []


def test_read_ledger_missing_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("APEX_LEDGER_DISABLED", raising=False)
    db = tmp_path / "missing.sqlite3"
    monkeypatch.setenv("APEX_LEDGER_PATH", str(db))
    snap = read_ledger_snapshot(limit=5)
    assert snap["ledger_enabled"] is True
    assert snap["runs"] == []
    assert "not found" in (snap.get("detail") or "").lower()


def test_read_ledger_roundtrip(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("APEX_LEDGER_DISABLED", raising=False)
    db = tmp_path / "ledger.sqlite3"
    monkeypatch.setenv("APEX_LEDGER_PATH", str(db))
    monkeypatch.setenv("APEX_LEDGER_STORE_STEP_DETAIL", "0")

    raw = ApexRunToolResult(
        verdict="needs_review",
        output="ok",
        metadata={
            "run_id": "rid-ledger-read-test",
            "mode": "text",
            "pipeline_steps": [
                {
                    "id": "ensemble",
                    "requirement": "required",
                    "ok": True,
                    "duration_ms": 2,
                    "detail": {},
                },
            ],
        },
    )
    fin = finalize_run_result(raw, run_id="rid-ledger-read-test", mode="text")
    asyncio.run(record_apex_run_to_ledger_if_enabled(fin))

    listed = read_ledger_snapshot(limit=10)
    assert listed["ledger_enabled"] is True
    assert len(listed["runs"]) == 1
    rid = listed["runs"][0]["run_id"]

    one = read_ledger_snapshot(limit=10, run_id=rid)
    assert len(one["runs"]) == 1
    assert len(one["steps"]) >= 1
    json.dumps(one)
