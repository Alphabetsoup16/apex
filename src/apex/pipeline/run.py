from __future__ import annotations

import asyncio
import time

from apex.ledger import record_apex_run_to_ledger_if_enabled
from apex.llm.interface import LLMClientFactory
from apex.models import ApexRunToolResult, Mode
from apex.observability.progress_events import (
    RUN_REJECTED,
    emit_progress,
    progress_run_scope,
)
from apex.pipeline.observability import finalize_run_result
from apex.pipeline.run_context import (
    ApexRunContext,
    build_apex_run_context,
    resolve_run_modes,
)
from apex.pipeline.run_execute import execute_apex_pipeline
from apex.pipeline.top_level_errors import (
    APEX_CAPACITY,
    APEX_RUN_TIMEOUT,
    apex_sanitized_error,
)
from apex.runtime.run_limits import load_run_limit_settings, run_concurrency_gate
from apex.safety.run_input_limits import validate_run_inputs

__all__ = ["LLMClientFactory", "apex_run", "resolve_run_modes"]


async def apex_run(
    *,
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
    run_id: str | None = None,
    supplementary_context: str | None = None,
    llm_client_factory: LLMClientFactory | None = None,
) -> ApexRunToolResult:
    """
    ``run_id`` — optional stable id (e.g. MCP pre-allocated). Default: random UUID.

    ``supplementary_context`` — optional operator-provided text included in **code** doc
    inspection only (not token streaming; bounded at MCP boundary).

    ``llm_client_factory`` — optional ``() -> LLMClient``; default loads from env/config
    (``apex.llm.loader.load_llm_client_from_env``). Embedders pass a factory; MCP omits.
    """
    ctx = build_apex_run_context(
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
        llm_client_factory=llm_client_factory,
    )

    bad_in = validate_run_inputs(
        prompt=prompt,
        diff=diff,
        repo_conventions=repo_conventions,
        known_good_baseline=known_good_baseline,
        language=language,
        output_mode=output_mode,
        supplementary_context=supplementary_context,
    )
    if bad_in is not None:
        return await _finalize_input_blocked(ctx, bad_in)

    limits = load_run_limit_settings()
    gate = run_concurrency_gate(limits.max_concurrent)
    slot_held = False
    if gate is not None:
        if not await gate.try_acquire():
            return await _finalize_capacity_blocked(ctx, limits.max_concurrent)
        slot_held = True

    outer_t0 = time.perf_counter()
    try:
        if limits.wall_ms > 0:
            try:
                return await asyncio.wait_for(
                    execute_apex_pipeline(ctx),
                    timeout=limits.wall_ms / 1000.0,
                )
            except TimeoutError:
                return await _finalize_wall_timeout(ctx, limits.wall_ms, outer_t0)
        return await execute_apex_pipeline(ctx)
    except asyncio.CancelledError:
        raise
    finally:
        if slot_held and gate is not None:
            await gate.release()


async def _finalize_input_blocked(ctx: ApexRunContext, bad_in: str) -> ApexRunToolResult:
    failed = ApexRunToolResult(
        verdict="blocked",
        output=f"APEX blocked: {bad_in}",
        adversarial_review=None,
        execution=None,
        metadata={
            **ctx.blocked_base_metadata(timings_total_ms=0),
            "error": bad_in,
            "input_validation": True,
        },
    )
    finalized = finalize_run_result(failed, run_id=ctx.run_id, mode=ctx.actual_mode)
    await record_apex_run_to_ledger_if_enabled(finalized)
    return finalized


async def _finalize_capacity_blocked(
    ctx: ApexRunContext,
    max_concurrent: int,
) -> ApexRunToolResult:
    with progress_run_scope(ctx.run_id):
        emit_progress(
            RUN_REJECTED,
            reason="capacity",
            max_concurrent=max_concurrent,
        )
    cap_msg = apex_sanitized_error(APEX_CAPACITY)
    failed = ApexRunToolResult(
        verdict="blocked",
        output=cap_msg,
        adversarial_review=None,
        execution=None,
        metadata={
            **ctx.blocked_base_metadata(timings_total_ms=0),
            "error_code": APEX_CAPACITY,
            "error": cap_msg,
            "error_type": "CapacityExceeded",
            "capacity_limit": max_concurrent,
        },
    )
    finalized = finalize_run_result(failed, run_id=ctx.run_id, mode=ctx.actual_mode)
    await record_apex_run_to_ledger_if_enabled(finalized)
    return finalized


async def _finalize_wall_timeout(
    ctx: ApexRunContext,
    wall_ms: int,
    outer_t0: float,
) -> ApexRunToolResult:
    total_ms = int((time.perf_counter() - outer_t0) * 1000)
    to_msg = apex_sanitized_error(APEX_RUN_TIMEOUT)
    with progress_run_scope(ctx.run_id):
        emit_progress(
            RUN_REJECTED,
            reason="wall_timeout",
            wall_timeout_ms=wall_ms,
        )
    failed = ApexRunToolResult(
        verdict="blocked",
        output=to_msg,
        adversarial_review=None,
        execution=None,
        metadata={
            **ctx.blocked_base_metadata(timings_total_ms=total_ms),
            "error_code": APEX_RUN_TIMEOUT,
            "error": to_msg,
            "error_type": "RunWallTimeout",
            "run_wall_timeout_ms": wall_ms,
        },
    )
    finalized = finalize_run_result(failed, run_id=ctx.run_id, mode=ctx.actual_mode)
    await record_apex_run_to_ledger_if_enabled(finalized)
    return finalized
