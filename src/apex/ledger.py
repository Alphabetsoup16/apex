from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apex.config.constants import LEDGER_QUERY_MAX_LIMIT
from apex.config.env import env_bool, env_int, env_str
from apex.models import ApexRunToolResult

_LOG = logging.getLogger(__name__)

LEDGER_QUERY_SCHEMA = "apex.ledger.query/v1"


def default_ledger_path() -> Path:
    """Default SQLite path when ``APEX_LEDGER_PATH`` is unset: ``~/.apex/ledger.sqlite3``."""
    return Path.home() / ".apex" / "ledger.sqlite3"


def resolve_ledger_db_path() -> Path | None:
    """
    Resolved ledger DB path for CLI / inspection, or ``None`` if ledger is disabled.

    - ``APEX_LEDGER_DISABLED=1`` (truthy) disables the ledger entirely.
    - Otherwise ``APEX_LEDGER_PATH`` overrides; if unset/empty, ``default_ledger_path()``.
    """
    if env_bool("APEX_LEDGER_DISABLED", default=False):
        return None
    override = env_str("APEX_LEDGER_PATH")
    if override:
        return Path(override).expanduser()
    return default_ledger_path()


@dataclass(frozen=True)
class LedgerConfig:
    db_path: Path
    store_step_detail: bool
    max_step_detail_chars: int
    busy_timeout_ms: int


def load_ledger_config() -> LedgerConfig | None:
    """
    Ledger is on by default at ``~/.apex/ledger.sqlite3``.

    - ``APEX_LEDGER_DISABLED=1`` turns it off.
    - ``APEX_LEDGER_PATH`` overrides the file location.
    """
    db_path = resolve_ledger_db_path()
    if db_path is None:
        return None
    store_step_detail = env_bool("APEX_LEDGER_STORE_STEP_DETAIL", default=False)
    max_step_detail_chars = env_int("APEX_LEDGER_MAX_DETAIL_CHARS", 65536)
    busy_timeout_ms = env_int("APEX_LEDGER_BUSY_TIMEOUT_MS", 2000)
    return LedgerConfig(
        db_path=db_path,
        store_step_detail=store_step_detail,
        max_step_detail_chars=max_step_detail_chars,
        busy_timeout_ms=busy_timeout_ms,
    )


def _utc_iso() -> str:
    # Keep formatting simple and stable for SQL/text comparisons.
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=True, separators=(",", ":"), default=str)


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            verdict TEXT NOT NULL,
            mode TEXT,
            llm_model TEXT,
            output_mode TEXT,
            convergence REAL,
            baseline_similarity REAL,
            run_wall_ms INTEGER,
            trace_validation_ok INTEGER,
            trace_validation_issues_json TEXT
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pipeline_steps (
            run_id TEXT NOT NULL,
            step_idx INTEGER NOT NULL,
            id TEXT,
            requirement TEXT,
            ok INTEGER NOT NULL,
            duration_ms INTEGER,
            detail_json TEXT,
            detail_truncated INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (run_id, step_idx)
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_steps_run_id ON pipeline_steps(run_id);")


def _record_sync(cfg: LedgerConfig, result: ApexRunToolResult) -> None:
    md = result.metadata or {}

    telemetry = md.get("telemetry") if isinstance(md.get("telemetry"), dict) else {}

    trace_validation = telemetry.get("trace_validation") if isinstance(telemetry, dict) else {}
    issues = trace_validation.get("issues") if isinstance(trace_validation, dict) else []
    if not isinstance(issues, list):
        issues = []

    run_wall_ms = telemetry.get("run_wall_ms") if isinstance(telemetry, dict) else None
    if not isinstance(run_wall_ms, int):
        run_wall_ms = None

    trace_validation_ok = 1 if trace_validation.get("ok") is True else 0

    run_id = str(md.get("run_id", ""))
    if not run_id:
        return

    runs_row = (
        run_id,
        _utc_iso(),
        result.verdict,
        md.get("mode"),
        md.get("llm_model"),
        md.get("output_mode"),
        md.get("convergence") if isinstance(md.get("convergence"), (int, float)) else None,
        md.get("baseline_similarity")
        if isinstance(md.get("baseline_similarity"), (int, float))
        else None,
        run_wall_ms,
        trace_validation_ok,
        _json_dumps(issues),
    )

    db_parent = cfg.db_path.parent
    if cfg.db_path.name != ":memory:":
        db_parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(cfg.db_path.as_posix(), timeout=cfg.busy_timeout_ms)
    try:
        _init_schema(conn)
        conn.execute(
            """
            INSERT OR REPLACE INTO runs (
                run_id, created_at, verdict, mode, llm_model, output_mode,
                convergence, baseline_similarity, run_wall_ms,
                trace_validation_ok, trace_validation_issues_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            runs_row,
        )

        steps_raw = md.get("pipeline_steps") or []
        if not isinstance(steps_raw, list):
            steps_raw = []

        for step_idx, step_row in enumerate(steps_raw):
            if not isinstance(step_row, dict):
                continue
            detail_raw = step_row.get("detail") if isinstance(step_row.get("detail"), dict) else {}
            ok = step_row.get("ok")
            ok_i = 1 if ok is True else 0
            duration_ms = step_row.get("duration_ms")
            if not isinstance(duration_ms, int):
                duration_ms = None

            detail_json: str | None
            detail_truncated = 0
            if cfg.store_step_detail:
                detail_str = _json_dumps(detail_raw)
                if len(detail_str) > cfg.max_step_detail_chars:
                    detail_json = detail_str[: cfg.max_step_detail_chars] + "...[TRUNCATED]"
                    detail_truncated = 1
                else:
                    detail_json = detail_str
            else:
                detail_json = None

            conn.execute(
                """
                INSERT OR REPLACE INTO pipeline_steps (
                    run_id,
                    step_idx,
                    id,
                    requirement,
                    ok,
                    duration_ms,
                    detail_json,
                    detail_truncated
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    run_id,
                    step_idx,
                    step_row.get("id"),
                    step_row.get("requirement"),
                    ok_i,
                    duration_ms,
                    detail_json,
                    detail_truncated,
                ),
            )
        conn.commit()
    finally:
        conn.close()


async def record_apex_run_to_ledger_if_enabled(result: ApexRunToolResult) -> None:
    cfg = load_ledger_config()
    if cfg is None:
        return
    try:
        await asyncio.to_thread(_record_sync, cfg, result)
    except Exception:
        # Ledger must never break the primary verification result path.
        _LOG.warning(
            "ledger write failed (tool result unchanged)",
            exc_info=True,
        )
        return


def _row_to_run_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "created_at": row["created_at"],
        "verdict": row["verdict"],
        "mode": row["mode"],
        "llm_model": row["llm_model"],
        "output_mode": row["output_mode"],
        "convergence": row["convergence"],
        "baseline_similarity": row["baseline_similarity"],
        "run_wall_ms": row["run_wall_ms"],
        "trace_validation_ok": bool(row["trace_validation_ok"]),
    }


def _row_to_step_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "step_idx": row["step_idx"],
        "id": row["id"],
        "requirement": row["requirement"],
        "ok": bool(row["ok"]),
        "duration_ms": row["duration_ms"],
        "detail_json": row["detail_json"],
        "detail_truncated": bool(row["detail_truncated"]),
    }


def read_ledger_snapshot(
    *,
    limit: int = 20,
    run_id: str | None = None,
) -> dict[str, Any]:
    """
    Read-only ledger snapshot for MCP / CLI (never raises for missing DB).

    - ``run_id`` set: return that run (if present) and its steps.
    - Otherwise: return up to ``limit`` recent runs (newest first), no steps.

    ``limit`` is clamped to ``1..LEDGER_QUERY_MAX_LIMIT``.
    """
    cfg = load_ledger_config()
    if cfg is None:
        return {
            "schema": LEDGER_QUERY_SCHEMA,
            "ledger_enabled": False,
            "db_path": None,
            "runs": [],
            "steps": [],
            "detail": "Ledger disabled (APEX_LEDGER_DISABLED).",
        }

    try:
        lim_raw = int(limit)
    except (TypeError, ValueError):
        lim_raw = 20
    lim = max(1, min(lim_raw, LEDGER_QUERY_MAX_LIMIT))
    path = cfg.db_path
    if not path.is_file():
        return {
            "schema": LEDGER_QUERY_SCHEMA,
            "ledger_enabled": True,
            "db_path": str(path),
            "runs": [],
            "steps": [],
            "detail": "Database file not found yet (no runs recorded).",
        }

    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if run_id:
            r = conn.execute(
                """
                SELECT run_id, created_at, verdict, mode, llm_model, output_mode,
                       convergence, baseline_similarity, run_wall_ms, trace_validation_ok
                FROM runs WHERE run_id = ?;
                """,
                (run_id,),
            ).fetchone()
            runs_out: list[dict[str, Any]] = []
            steps_out: list[dict[str, Any]] = []
            if r is not None:
                runs_out.append(_row_to_run_dict(r))
                step_rows = conn.execute(
                    """
                    SELECT run_id, step_idx, id, requirement, ok, duration_ms,
                           detail_json, detail_truncated
                    FROM pipeline_steps
                    WHERE run_id = ?
                    ORDER BY step_idx ASC;
                    """,
                    (run_id,),
                ).fetchall()
                steps_out = [_row_to_step_dict(sr) for sr in step_rows]
            return {
                "schema": LEDGER_QUERY_SCHEMA,
                "ledger_enabled": True,
                "db_path": str(path),
                "runs": runs_out,
                "steps": steps_out,
                "detail": None if runs_out else f"No run found for run_id={run_id!r}.",
            }

        rows = conn.execute(
            """
            SELECT run_id, created_at, verdict, mode, llm_model, output_mode,
                   convergence, baseline_similarity, run_wall_ms, trace_validation_ok
            FROM runs
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            (lim,),
        ).fetchall()
        return {
            "schema": LEDGER_QUERY_SCHEMA,
            "ledger_enabled": True,
            "db_path": str(path),
            "runs": [_row_to_run_dict(r) for r in rows],
            "steps": [],
            "detail": None,
        }
    except sqlite3.Error as e:
        return {
            "schema": LEDGER_QUERY_SCHEMA,
            "ledger_enabled": True,
            "db_path": str(path),
            "runs": [],
            "steps": [],
            "detail": f"SQLite read error: {e}",
        }
    finally:
        conn.close()
