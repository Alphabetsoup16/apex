import asyncio
import io
import json
import logging
import sqlite3
import sys
from pathlib import Path

import pytest

import apex.ledger as ledger_mod
import apex.pipeline.run as pipeline_run
import apex.pipeline.run_context as run_context
import apex.pipeline.text_mode as text_mode
from apex.ledger import record_apex_run_to_ledger_if_enabled
from apex.models import AdversarialReview, ApexRunToolResult, Finding, TextCompletion
from apex.pipeline.observability import finalize_run_result
from tests.fakes import FakeLLMClient


def _read_json_column(conn: sqlite3.Connection, sql: str, params: tuple) -> object:
    row = conn.execute(sql, params).fetchone()
    assert row is not None
    return json.loads(row[0]) if row[0] is not None else None


def test_ledger_disabled_does_not_create_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("APEX_LEDGER_DISABLED", "1")
    monkeypatch.delenv("APEX_LEDGER_PATH", raising=False)
    monkeypatch.delenv("APEX_LEDGER_STORE_STEP_DETAIL", raising=False)

    default_db = tmp_path / ".apex" / "ledger.sqlite3"
    assert not default_db.exists()

    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-text"))

    async def fake_generate_text_variants(*, client, prompt: str, config):
        assert prompt == "hello"
        return [TextCompletion(answer="HELLO WORLD", key_claims=["x"])]

    async def fake_review_text(*, client, task_prompt: str, candidate, max_tokens: int):
        return AdversarialReview(
            findings=[Finding(severity="low", type="t", confidence=0.1, evidence="e")]
        )

    monkeypatch.setattr(text_mode, "generate_text_variants", fake_generate_text_variants)
    monkeypatch.setattr(text_mode, "review_text", fake_review_text)
    monkeypatch.setattr(text_mode, "text_convergence", lambda variants: 0.99)
    monkeypatch.setattr(text_mode, "select_best_text", lambda variants: 0)
    monkeypatch.setattr(text_mode, "audit_chain_of_thought", lambda *args, **kwargs: [])
    monkeypatch.setattr(text_mode, "decide_verdict", lambda signals: "high_verified")

    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="hello",
            mode="text",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=False,
            known_good_baseline="HELLO WORLD",
        )
    )
    assert result.metadata["baseline_similarity"] is not None
    assert not default_db.exists()


def test_ledger_enabled_store_step_detail_off(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.delenv("APEX_LEDGER_DISABLED", raising=False)
    db_path = tmp_path / "ledger.sqlite3"
    monkeypatch.setenv("APEX_LEDGER_PATH", str(db_path))
    monkeypatch.setenv("APEX_LEDGER_STORE_STEP_DETAIL", "0")

    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-text"))

    async def fake_generate_text_variants(*, client, prompt: str, config):
        return [TextCompletion(answer="HELLO WORLD", key_claims=["x"])]

    async def fake_review_text(*, client, task_prompt: str, candidate, max_tokens: int):
        return AdversarialReview(
            findings=[Finding(severity="low", type="t", confidence=0.1, evidence="e")]
        )

    monkeypatch.setattr(text_mode, "generate_text_variants", fake_generate_text_variants)
    monkeypatch.setattr(text_mode, "review_text", fake_review_text)
    monkeypatch.setattr(text_mode, "text_convergence", lambda variants: 0.99)
    monkeypatch.setattr(text_mode, "select_best_text", lambda variants: 0)
    monkeypatch.setattr(text_mode, "audit_chain_of_thought", lambda *args, **kwargs: [])
    monkeypatch.setattr(text_mode, "decide_verdict", lambda signals: "high_verified")

    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="hello",
            mode="text",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=False,
            known_good_baseline="HELLO WORLD",
        )
    )

    assert db_path.exists()
    run_id = result.metadata["run_id"]

    conn = sqlite3.connect(db_path.as_posix())
    try:
        run_row = conn.execute(
            "SELECT verdict, baseline_similarity, trace_validation_ok FROM runs WHERE run_id=?;",
            (run_id,),
        ).fetchone()
        assert run_row is not None
        verdict, baseline_similarity, trace_validation_ok = run_row
        assert verdict == "high_verified"
        assert baseline_similarity == result.metadata["baseline_similarity"]
        assert trace_validation_ok == 1

        detail_json = conn.execute(
            "SELECT detail_json FROM pipeline_steps WHERE run_id=? AND id='baseline_alignment';",
            (run_id,),
        ).fetchone()[0]
        assert detail_json is None
    finally:
        conn.close()


def test_ledger_enabled_store_step_detail_on(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.delenv("APEX_LEDGER_DISABLED", raising=False)
    db_path = tmp_path / "ledger.sqlite3"
    monkeypatch.setenv("APEX_LEDGER_PATH", str(db_path))
    monkeypatch.setenv("APEX_LEDGER_STORE_STEP_DETAIL", "1")
    monkeypatch.setenv("APEX_LEDGER_MAX_DETAIL_CHARS", "100000")

    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-text"))

    async def fake_generate_text_variants(*, client, prompt: str, config):
        return [TextCompletion(answer="HELLO WORLD", key_claims=["x"])]

    async def fake_review_text(*, client, task_prompt: str, candidate, max_tokens: int):
        return AdversarialReview(findings=[])

    monkeypatch.setattr(text_mode, "generate_text_variants", fake_generate_text_variants)
    monkeypatch.setattr(text_mode, "review_text", fake_review_text)
    monkeypatch.setattr(text_mode, "text_convergence", lambda variants: 0.99)
    monkeypatch.setattr(text_mode, "select_best_text", lambda variants: 0)
    monkeypatch.setattr(text_mode, "audit_chain_of_thought", lambda *args, **kwargs: [])
    monkeypatch.setattr(text_mode, "decide_verdict", lambda signals: "high_verified")

    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="hello",
            mode="text",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=False,
            known_good_baseline="HELLO WORLD",
        )
    )

    assert db_path.exists()
    run_id = result.metadata["run_id"]

    conn = sqlite3.connect(db_path.as_posix())
    try:
        detail_obj = _read_json_column(
            conn,
            "SELECT detail_json FROM pipeline_steps WHERE run_id=? AND id='baseline_alignment';",
            (run_id,),
        )
        assert isinstance(detail_obj, dict)
        assert float(detail_obj["similarity"]) == pytest.approx(1.0)
        assert detail_obj["downgraded"] is False
    finally:
        conn.close()


def test_resolve_ledger_db_path_default_under_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("APEX_LEDGER_DISABLED", raising=False)
    monkeypatch.delenv("APEX_LEDGER_PATH", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert ledger_mod.resolve_ledger_db_path() == tmp_path / ".apex" / "ledger.sqlite3"


def test_resolve_ledger_db_path_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APEX_LEDGER_DISABLED", "1")
    assert ledger_mod.resolve_ledger_db_path() is None


def test_ledger_summary_missing_file_ok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("APEX_LEDGER_DISABLED", raising=False)
    monkeypatch.setenv("APEX_LEDGER_PATH", str(tmp_path / "new.sqlite3"))

    from apex.cli import ledger_cmd

    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    ledger_cmd.cmd_ledger_summary()
    assert "not found yet" in buf.getvalue()


def test_ledger_summary_disabled_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APEX_LEDGER_DISABLED", "1")

    from apex.cli import ledger_cmd

    with pytest.raises(SystemExit) as exc:
        ledger_cmd.cmd_ledger_summary()
    assert exc.value.code == 1


def test_ledger_summary_with_one_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("APEX_LEDGER_DISABLED", raising=False)
    db_path = tmp_path / "ledger.sqlite3"
    monkeypatch.setenv("APEX_LEDGER_PATH", str(db_path))

    conn = sqlite3.connect(db_path.as_posix())
    try:
        ledger_mod._init_schema(conn)
        conn.execute(
            """
            INSERT INTO runs (
                run_id, created_at, verdict, mode, llm_model, output_mode,
                convergence, baseline_similarity, run_wall_ms,
                trace_validation_ok, trace_validation_issues_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "rid-1",
                "2020-01-01T00:00:00Z",
                "needs_review",
                "text",
                "m",
                "candidate",
                0.9,
                None,
                100,
                1,
                "[]",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    from apex.cli import ledger_cmd

    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    ledger_cmd.cmd_ledger_summary()
    out = buf.getvalue()
    assert "Total runs: 1" in out
    assert "needs_review" in out
    assert "rid-1" in out


def test_ledger_write_failure_logs_warning(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("APEX_LEDGER_DISABLED", raising=False)
    db = tmp_path / "ledger.sqlite3"
    monkeypatch.setenv("APEX_LEDGER_PATH", str(db))

    raw = ApexRunToolResult(
        verdict="needs_review",
        output="ok",
        metadata={
            "run_id": "rid-log-test",
            "mode": "text",
            "pipeline_steps": [],
        },
    )
    fin = finalize_run_result(raw, run_id="rid-log-test", mode="text")

    def _boom(*_a: object, **_k: object) -> None:
        raise OSError("simulated ledger failure")

    monkeypatch.setattr(ledger_mod, "_record_sync", _boom)

    caplog.set_level(logging.WARNING, logger="apex.ledger")
    asyncio.run(record_apex_run_to_ledger_if_enabled(fin))
    assert any("ledger write failed" in r.message for r in caplog.records)
