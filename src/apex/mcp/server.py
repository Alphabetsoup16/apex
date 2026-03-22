from __future__ import annotations

import asyncio
import uuid
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from apex.ledger import read_ledger_snapshot, record_apex_run_to_ledger_if_enabled
from apex.mcp.diagnostics import build_config_describe_snapshot, build_health_snapshot
from apex.mcp.input_guard import validate_correlation_id
from apex.mcp.run_registry import (
    bind_correlation_task,
    cancel_run_by_correlation_id,
    reserve_correlation_slot,
    unregister_correlation,
)
from apex.models import ApexRunToolResult, Mode
from apex.pipeline import apex_run, resolve_run_modes
from apex.pipeline.guard_metadata import blocked_run_base_metadata, clamp_ensemble_runs
from apex.pipeline.observability import finalize_run_result
from apex.pipeline.top_level_errors import (
    APEX_CANCELLED,
    APEX_MCP_CORRELATION,
    APEX_VALIDATION,
    apex_sanitized_error,
)
from apex.repo_context import (
    glob_disabled_payload,
    glob_payload,
    load_repo_context_config,
    read_disabled_payload,
    read_file_payload,
    status_payload,
)


def _finalize_blocked(
    *,
    run_id: str,
    actual_mode: Literal["text", "code"],
    mode_request: Mode,
    inferred: Literal["text", "code"],
    output: str,
    error: str,
    ensemble_runs_requested: int,
    ensemble_runs_effective: int,
    max_tokens: int,
    output_mode: str,
    code_ground_truth: bool,
    timings_total_ms: int = 0,
    extra: dict[str, Any] | None = None,
) -> ApexRunToolResult:
    md: dict[str, Any] = {
        **blocked_run_base_metadata(
            run_id=run_id,
            actual_mode=actual_mode,
            mode=mode_request,
            inferred=inferred,
            ensemble_runs_requested=ensemble_runs_requested,
            ensemble_runs_effective=ensemble_runs_effective,
            max_tokens=max_tokens,
            output_mode=output_mode,
            code_ground_truth=code_ground_truth,
            timings_total_ms=timings_total_ms,
        ),
        "error": error,
    }
    if extra:
        md.update(extra)
    raw = ApexRunToolResult(
        verdict="blocked",
        output=output,
        adversarial_review=None,
        execution=None,
        metadata=md,
    )
    return finalize_run_result(raw, run_id=run_id, mode=actual_mode)


def create_mcp_server() -> FastMCP:
    mcp = FastMCP("apex", json_response=True)

    @mcp.tool()
    async def health() -> dict[str, object]:
        """Process snapshot: version, ledger on/off, execution backend configured (no secrets)."""
        return build_health_snapshot()

    @mcp.tool()
    async def describe_config() -> dict[str, object]:
        """Effective LLM config shape from file + env (API keys: set/unset only, never values)."""
        return build_config_describe_snapshot()

    @mcp.tool()
    async def repo_context_status() -> dict[str, object]:
        """
        Repo filesystem context: whether allowlisted read is enabled and effective limits.
        Off unless APEX_REPO_CONTEXT_ROOT is set (see docs/repo-context.md).
        """
        return status_payload(load_repo_context_config())

    @mcp.tool()
    async def repo_read_file(relative_path: str) -> dict[str, object]:
        """
        Read a UTF-8 text file under APEX_REPO_CONTEXT_ROOT (root-relative path, no ..).
        Bounded by APEX_REPO_CONTEXT_MAX_FILE_BYTES; returns truncated + flag if larger.
        """
        cfg = load_repo_context_config()
        if cfg is None:
            return read_disabled_payload()
        return await asyncio.to_thread(read_file_payload, cfg, relative_path)

    @mcp.tool()
    async def repo_glob(pattern: str) -> dict[str, object]:
        """
        List files under the repo root matching a root-relative glob pattern (pathlib semantics).
        Capped at APEX_REPO_CONTEXT_MAX_GLOB_RESULTS; truncated=true if more exist.
        """
        cfg = load_repo_context_config()
        if cfg is None:
            return glob_disabled_payload()
        return await asyncio.to_thread(glob_payload, cfg, pattern)

    @mcp.tool()
    async def ledger_query(
        limit: int = 20,
        run_id: str | None = None,
    ) -> dict[str, object]:
        """
        Read-only SQLite ledger: recent runs, or one run + pipeline steps by ``run_id``.
        ``limit`` is clamped (see ``LEDGER_QUERY_MAX_LIMIT``). Safe when ledger disabled.
        """
        return read_ledger_snapshot(limit=limit, run_id=run_id)

    @mcp.tool()
    async def cancel_run(correlation_id: str) -> dict[str, object]:
        """
        Request cancellation for an in-flight ``run`` that registered the same ``correlation_id``.
        Best-effort: cancellation applies at the next ``await`` inside the pipeline.
        """
        if not correlation_id.strip():
            return {
                "schema": "apex.cancel_run/v1",
                "correlation_id": correlation_id,
                "status": "invalid_id",
                "detail": "correlation_id is required",
            }
        err = validate_correlation_id(correlation_id)
        if err:
            return {
                "schema": "apex.cancel_run/v1",
                "correlation_id": correlation_id,
                "status": "invalid_id",
                "detail": err,
            }
        cid = correlation_id.strip()
        return await cancel_run_by_correlation_id(cid)

    @mcp.tool()
    async def run(
        prompt: str,
        mode: Mode = "auto",
        ensemble_runs: int = 3,
        max_tokens: int = 1024,
        code_ground_truth: bool = False,
        known_good_baseline: str | None = None,
        language: str | None = None,
        diff: str | None = None,
        repo_conventions: str | None = None,
        output_mode: str = "candidate",
        correlation_id: str | None = None,
        supplementary_context: str | None = None,
    ):
        """
        Run APEX verification on a prompt.

        Optional ``correlation_id`` (alphanumeric plus ``._-``) registers this run for
        ``cancel_run``. Optional ``supplementary_context`` is passed to **code** doc inspection
        only (bounded size; not live repo index).

        For text: returns the best candidate answer plus structured adversarial findings.
        Optional `known_good_baseline` can downgrade `high_verified` when outputs diverge.

        For code: generates a Python solution + pytest tests. If `code_ground_truth=true`,
        it executes tests via `APEX_EXECUTION_BACKEND_URL`, then returns a deterministic verdict.
        Also performs chain-of-thought auditing on generated solution content.

        `mode="auto"` uses a small keyword heuristic and may misclassify; pass `mode` explicitly
        when behavior must be predictable. `ensemble_runs` is clamped to 2-3; see response
        metadata `ensemble_runs_requested` vs `ensemble_runs_effective`.
        """
        run_id = str(uuid.uuid4())
        actual_mode, inferred = resolve_run_modes(prompt=prompt, mode=mode)
        ens_req, ens_eff = clamp_ensemble_runs(ensemble_runs)

        cid_err = validate_correlation_id(correlation_id)
        if cid_err:
            fin = _finalize_blocked(
                run_id=run_id,
                actual_mode=actual_mode,
                mode_request=mode,
                inferred=inferred,
                output=f"APEX blocked: {cid_err}",
                error=cid_err,
                ensemble_runs_requested=ens_req,
                ensemble_runs_effective=ens_eff,
                max_tokens=max_tokens,
                output_mode=output_mode,
                code_ground_truth=code_ground_truth,
                extra={
                    "input_validation": True,
                    "error_code": APEX_VALIDATION,
                    "error_type": "CorrelationIdValidation",
                },
            )
            await record_apex_run_to_ledger_if_enabled(fin)
            return fin.model_dump(by_alias=True)

        cid = correlation_id.strip() if correlation_id else None

        if cid:
            slot_err = await reserve_correlation_slot(cid)
            if slot_err:
                dup_msg = apex_sanitized_error(APEX_MCP_CORRELATION)
                fin = _finalize_blocked(
                    run_id=run_id,
                    actual_mode=actual_mode,
                    mode_request=mode,
                    inferred=inferred,
                    output=f"APEX blocked: {dup_msg}",
                    error=dup_msg,
                    ensemble_runs_requested=ens_req,
                    ensemble_runs_effective=ens_eff,
                    max_tokens=max_tokens,
                    output_mode=output_mode,
                    code_ground_truth=code_ground_truth,
                    extra={
                        "mcp_correlation_rejected": True,
                        "error_code": APEX_MCP_CORRELATION,
                        "error_type": "CorrelationIdConflict",
                    },
                )
                await record_apex_run_to_ledger_if_enabled(fin)
                return fin.model_dump(by_alias=True)

        try:
            task = asyncio.create_task(
                apex_run(
                    prompt=prompt,
                    mode=mode,
                    ensemble_runs=ensemble_runs,
                    max_tokens=max_tokens,
                    code_ground_truth=code_ground_truth,
                    known_good_baseline=known_good_baseline,
                    language=language,
                    diff=diff,
                    repo_conventions=repo_conventions,
                    output_mode=output_mode,
                    run_id=run_id,
                    supplementary_context=supplementary_context,
                )
            )
            if cid:
                await bind_correlation_task(cid, task)
            finalized = await task
        except asyncio.CancelledError:
            can_msg = apex_sanitized_error(APEX_CANCELLED)
            fin = _finalize_blocked(
                run_id=run_id,
                actual_mode=actual_mode,
                mode_request=mode,
                inferred=inferred,
                output=f"APEX blocked: {can_msg}",
                error=can_msg,
                ensemble_runs_requested=ens_req,
                ensemble_runs_effective=ens_eff,
                max_tokens=max_tokens,
                output_mode=output_mode,
                code_ground_truth=code_ground_truth,
                extra={
                    "cancelled": True,
                    "error_code": APEX_CANCELLED,
                    "error_type": "CancelledError",
                },
            )
            await record_apex_run_to_ledger_if_enabled(fin)
            out = fin.model_dump(by_alias=True)
        else:
            out = finalized.model_dump(by_alias=True)
        finally:
            if cid:
                await unregister_correlation(cid)
        return out

    return mcp
