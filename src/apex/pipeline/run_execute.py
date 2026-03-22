"""LLM pipeline body for ``apex_run`` (text/code modes, finalize, ledger dispatch)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Literal

from apex.config.conventions import load_effective_conventions
from apex.config.env import env_str
from apex.generation.ensemble import EnsembleConfig
from apex.ledger import load_ledger_config, record_apex_run_to_ledger_if_enabled
from apex.models import ApexRunToolResult
from apex.observability.progress_events import (
    CLIENT_READY,
    FINALIZE_BEGIN,
    FINALIZE_END,
    LEDGER_DISPATCH,
    PIPELINE_ENTER,
    PIPELINE_EXIT,
    RUN_COMPLETE,
    RUN_ERROR,
    RUN_START,
    emit_progress,
    progress_run_scope,
)
from apex.pipeline.code_mode import run_code_mode
from apex.pipeline.helpers import temperatures_for_runs
from apex.pipeline.observability import finalize_run_result
from apex.pipeline.run_context import ApexRunContext
from apex.pipeline.text_mode import run_text_mode
from apex.pipeline.top_level_errors import build_top_level_error_metadata

_LOG = logging.getLogger(__name__)


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


async def execute_apex_pipeline(ctx: ApexRunContext) -> ApexRunToolResult:
    """
    Run text or code pipeline, finalize, optional ledger write.

    Caller owns concurrency gate, wall timeout, and input validation.
    """
    t_wall_start = time.perf_counter()
    run_id = ctx.run_id
    actual_mode: Literal["text", "code"] = ctx.actual_mode
    ensemble_runs = ctx.ensemble_runs_effective

    with progress_run_scope(run_id):
        emit_progress(
            RUN_START,
            mode_request=ctx.mode,
            mode_effective=actual_mode,
            mode_inferred=ctx.inferred if ctx.mode == "auto" else None,
            ensemble_runs_effective=ensemble_runs,
            ensemble_runs_requested=ctx.ensemble_runs_requested,
            max_tokens=ctx.max_tokens,
            code_ground_truth=ctx.code_ground_truth,
            output_mode=ctx.output_mode,
        )
        try:
            client = ctx.llm_client_factory()
            effective_conventions = load_effective_conventions(
                repo_conventions=ctx.repo_conventions,
            )
            emit_progress(
                CLIENT_READY,
                llm_provider=(env_str("APEX_LLM_PROVIDER") or "anthropic"),
            )
            t_total_start = time.perf_counter()
            temps = temperatures_for_runs(ensemble_runs)
            cfg = EnsembleConfig(runs=ensemble_runs, temperatures=temps, max_tokens=ctx.max_tokens)

            emit_progress(PIPELINE_ENTER, pipeline=actual_mode)
            if actual_mode == "text":
                result = await run_text_mode(
                    client=client,
                    prompt=ctx.prompt,
                    cfg=cfg,
                    ensemble_runs=ensemble_runs,
                    max_tokens=ctx.max_tokens,
                    actual_mode=actual_mode,
                    run_id=run_id,
                    t_total_start=t_total_start,
                    known_good_baseline=ctx.known_good_baseline,
                    language=ctx.language,
                    diff=ctx.diff,
                    repo_conventions=effective_conventions,
                    output_mode=ctx.output_mode,
                )
            else:
                result = await run_code_mode(
                    client=client,
                    prompt=ctx.prompt,
                    cfg=cfg,
                    ensemble_runs=ensemble_runs,
                    max_tokens=ctx.max_tokens,
                    actual_mode=actual_mode,
                    code_ground_truth=ctx.code_ground_truth,
                    run_id=run_id,
                    t_total_start=t_total_start,
                    known_good_baseline=ctx.known_good_baseline,
                    language=ctx.language,
                    diff=ctx.diff,
                    repo_conventions=effective_conventions,
                    output_mode=ctx.output_mode,
                    supplementary_context=ctx.supplementary_context,
                )
            emit_progress(
                PIPELINE_EXIT,
                pipeline=actual_mode,
                verdict=result.verdict,
            )
            result = _annotate_ensemble_runs_metadata(
                result,
                ensemble_runs_requested=ctx.ensemble_runs_requested,
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
                    **ctx.blocked_base_metadata(timings_total_ms=total_ms),
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
