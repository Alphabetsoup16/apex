from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Literal

from apex.config.conventions import load_effective_conventions
from apex.generation.ensemble import EnsembleConfig
from apex.ledger import load_ledger_config, record_apex_run_to_ledger_if_enabled
from apex.llm.loader import load_llm_client_from_env
from apex.models import ApexRunToolResult, Mode
from apex.observability.progress_events import (
    CLIENT_READY,
    FINALIZE_BEGIN,
    FINALIZE_END,
    LEDGER_DISPATCH,
    PIPELINE_ENTER,
    PIPELINE_EXIT,
    RUN_COMPLETE,
    RUN_ERROR,
    RUN_REJECTED,
    RUN_START,
    emit_progress,
    progress_run_scope,
)
from apex.pipeline.code_mode import run_code_mode
from apex.pipeline.guard_metadata import blocked_run_base_metadata, clamp_ensemble_runs
from apex.pipeline.helpers import infer_mode_from_prompt, temperatures_for_runs
from apex.pipeline.observability import finalize_run_result
from apex.pipeline.text_mode import run_text_mode
from apex.pipeline.top_level_errors import (
    APEX_CAPACITY,
    APEX_RUN_TIMEOUT,
    apex_sanitized_error,
    build_top_level_error_metadata,
)
from apex.runtime.run_limits import load_run_limit_settings, run_concurrency_gate
from apex.safety.run_input_limits import validate_run_inputs

_LOG = logging.getLogger(__name__)


def resolve_run_modes(
    *, prompt: str, mode: Mode
) -> tuple[Literal["text", "code"], Literal["text", "code"]]:
    """
    Match ``apex_run`` mode resolution: ``inferred`` from prompt heuristics vs explicit request.
    """
    inferred: Literal["text", "code"] = infer_mode_from_prompt(prompt)
    if mode == "auto":
        actual_mode: Literal["text", "code"] = inferred
    else:
        actual_mode = "text" if mode == "text" else "code"
    return actual_mode, inferred


def _annotate_ensemble_runs_metadata(
    result: ApexRunToolResult,
    *,
    ensemble_runs_requested: int,
    ensemble_runs_effective: int,
) -> ApexRunToolResult:
    meta = {
        **result.metadata,
        "ensemble_runs_requested": ensemble_runs_requested,
        "ensemble_runs_effective": ensemble_runs_effective,
    }
    return result.model_copy(update={"metadata": meta})


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
) -> ApexRunToolResult:
    """
    ``run_id`` — optional stable id (e.g. MCP pre-allocated). Default: random UUID.

    ``supplementary_context`` — optional operator-provided text included in **code** doc
    inspection only (not token streaming; bounded at MCP boundary).
    """
    run_id = run_id or str(uuid.uuid4())
    ensemble_runs_requested, ensemble_runs = clamp_ensemble_runs(ensemble_runs)
    actual_mode, inferred = resolve_run_modes(prompt=prompt, mode=mode)

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
        failed = ApexRunToolResult(
            verdict="blocked",
            output=f"APEX blocked: {bad_in}",
            adversarial_review=None,
            execution=None,
            metadata={
                **blocked_run_base_metadata(
                    run_id=run_id,
                    actual_mode=actual_mode,
                    mode=mode,
                    inferred=inferred,
                    ensemble_runs_requested=ensemble_runs_requested,
                    ensemble_runs_effective=ensemble_runs,
                    max_tokens=max_tokens,
                    output_mode=output_mode,
                    code_ground_truth=code_ground_truth,
                    timings_total_ms=0,
                ),
                "error": bad_in,
                "input_validation": True,
            },
        )
        finalized = finalize_run_result(failed, run_id=run_id, mode=actual_mode)
        await record_apex_run_to_ledger_if_enabled(finalized)
        return finalized

    limits = load_run_limit_settings()
    gate = run_concurrency_gate(limits.max_concurrent)
    slot_held = False
    if gate is not None:
        if not await gate.try_acquire():
            with progress_run_scope(run_id):
                emit_progress(
                    RUN_REJECTED,
                    reason="capacity",
                    max_concurrent=limits.max_concurrent,
                )
            cap_msg = apex_sanitized_error(APEX_CAPACITY)
            failed = ApexRunToolResult(
                verdict="blocked",
                output=cap_msg,
                adversarial_review=None,
                execution=None,
                metadata={
                    **blocked_run_base_metadata(
                        run_id=run_id,
                        actual_mode=actual_mode,
                        mode=mode,
                        inferred=inferred,
                        ensemble_runs_requested=ensemble_runs_requested,
                        ensemble_runs_effective=ensemble_runs,
                        max_tokens=max_tokens,
                        output_mode=output_mode,
                        code_ground_truth=code_ground_truth,
                        timings_total_ms=0,
                    ),
                    "error_code": APEX_CAPACITY,
                    "error": cap_msg,
                    "error_type": "CapacityExceeded",
                    "capacity_limit": limits.max_concurrent,
                },
            )
            finalized = finalize_run_result(failed, run_id=run_id, mode=actual_mode)
            await record_apex_run_to_ledger_if_enabled(finalized)
            return finalized
        slot_held = True

    outer_t0 = time.perf_counter()

    async def _pipeline() -> ApexRunToolResult:
        t_wall_start = time.perf_counter()
        with progress_run_scope(run_id):
            emit_progress(
                RUN_START,
                mode_request=mode,
                mode_effective=actual_mode,
                mode_inferred=inferred if mode == "auto" else None,
                ensemble_runs_effective=ensemble_runs,
                ensemble_runs_requested=ensemble_runs_requested,
                max_tokens=max_tokens,
                code_ground_truth=code_ground_truth,
                output_mode=output_mode,
            )
            try:
                client = load_llm_client_from_env()
                effective_conventions = load_effective_conventions(
                    repo_conventions=repo_conventions,
                )
                emit_progress(
                    CLIENT_READY,
                    llm_provider=(os.environ.get("APEX_LLM_PROVIDER", "").strip() or "anthropic"),
                )
                t_total_start = time.perf_counter()
                temps = temperatures_for_runs(ensemble_runs)
                cfg = EnsembleConfig(runs=ensemble_runs, temperatures=temps, max_tokens=max_tokens)

                emit_progress(PIPELINE_ENTER, pipeline=actual_mode)
                if actual_mode == "text":
                    result = await run_text_mode(
                        client=client,
                        prompt=prompt,
                        cfg=cfg,
                        ensemble_runs=ensemble_runs,
                        max_tokens=max_tokens,
                        actual_mode=actual_mode,
                        run_id=run_id,
                        t_total_start=t_total_start,
                        known_good_baseline=known_good_baseline,
                        language=language,
                        diff=diff,
                        repo_conventions=effective_conventions,
                        output_mode=output_mode,
                    )
                else:
                    result = await run_code_mode(
                        client=client,
                        prompt=prompt,
                        cfg=cfg,
                        ensemble_runs=ensemble_runs,
                        max_tokens=max_tokens,
                        actual_mode=actual_mode,
                        code_ground_truth=code_ground_truth,
                        run_id=run_id,
                        t_total_start=t_total_start,
                        known_good_baseline=known_good_baseline,
                        language=language,
                        diff=diff,
                        repo_conventions=effective_conventions,
                        output_mode=output_mode,
                        supplementary_context=supplementary_context,
                    )
                emit_progress(
                    PIPELINE_EXIT,
                    pipeline=actual_mode,
                    verdict=result.verdict,
                )
                result = _annotate_ensemble_runs_metadata(
                    result,
                    ensemble_runs_requested=ensemble_runs_requested,
                    ensemble_runs_effective=ensemble_runs,
                )
                emit_progress(FINALIZE_BEGIN)
                finalized = finalize_run_result(result, run_id=run_id, mode=actual_mode)
                emit_progress(FINALIZE_END)
                emit_progress(LEDGER_DISPATCH, ledger_enabled=load_ledger_config() is not None)
                await record_apex_run_to_ledger_if_enabled(finalized)
                emit_progress(RUN_COMPLETE, verdict=finalized.verdict)
                return finalized
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _LOG.exception("apex_run: uncaught exception inside pipeline")
                emit_progress(RUN_ERROR, error_type=type(e).__name__)
                total_ms = int((time.perf_counter() - t_wall_start) * 1000)
                err_meta = build_top_level_error_metadata(e)
                failed = ApexRunToolResult(
                    verdict="blocked",
                    output=f"APEX blocked: {err_meta['error']}",
                    adversarial_review=None,
                    execution=None,
                    metadata={
                        **blocked_run_base_metadata(
                            run_id=run_id,
                            actual_mode=actual_mode,
                            mode=mode,
                            inferred=inferred,
                            ensemble_runs_requested=ensemble_runs_requested,
                            ensemble_runs_effective=ensemble_runs,
                            max_tokens=max_tokens,
                            output_mode=output_mode,
                            code_ground_truth=code_ground_truth,
                            timings_total_ms=total_ms,
                        ),
                        **err_meta,
                    },
                )
                emit_progress(FINALIZE_BEGIN)
                finalized = finalize_run_result(failed, run_id=run_id, mode=actual_mode)
                emit_progress(FINALIZE_END)
                emit_progress(LEDGER_DISPATCH, ledger_enabled=load_ledger_config() is not None)
                await record_apex_run_to_ledger_if_enabled(finalized)
                emit_progress(RUN_COMPLETE, verdict=finalized.verdict)
                return finalized

    try:
        if limits.wall_ms > 0:
            try:
                return await asyncio.wait_for(_pipeline(), timeout=limits.wall_ms / 1000.0)
            except TimeoutError:
                total_ms = int((time.perf_counter() - outer_t0) * 1000)
                to_msg = apex_sanitized_error(APEX_RUN_TIMEOUT)
                with progress_run_scope(run_id):
                    emit_progress(
                        RUN_REJECTED,
                        reason="wall_timeout",
                        wall_timeout_ms=limits.wall_ms,
                    )
                failed = ApexRunToolResult(
                    verdict="blocked",
                    output=to_msg,
                    adversarial_review=None,
                    execution=None,
                    metadata={
                        **blocked_run_base_metadata(
                            run_id=run_id,
                            actual_mode=actual_mode,
                            mode=mode,
                            inferred=inferred,
                            ensemble_runs_requested=ensemble_runs_requested,
                            ensemble_runs_effective=ensemble_runs,
                            max_tokens=max_tokens,
                            output_mode=output_mode,
                            code_ground_truth=code_ground_truth,
                            timings_total_ms=total_ms,
                        ),
                        "error_code": APEX_RUN_TIMEOUT,
                        "error": to_msg,
                        "error_type": "RunWallTimeout",
                        "run_wall_timeout_ms": limits.wall_ms,
                    },
                )
                finalized = finalize_run_result(failed, run_id=run_id, mode=actual_mode)
                await record_apex_run_to_ledger_if_enabled(finalized)
                return finalized
        return await _pipeline()
    except asyncio.CancelledError:
        raise
    finally:
        if slot_held and gate is not None:
            await gate.release()
