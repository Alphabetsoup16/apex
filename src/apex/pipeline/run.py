from __future__ import annotations

import asyncio
import time
import uuid
from typing import Literal

from apex.config.constants import ENSEMBLE_RUNS_MAX_EFFECTIVE, ENSEMBLE_RUNS_MIN_EFFECTIVE
from apex.config.conventions import load_effective_conventions
from apex.generation.ensemble import EnsembleConfig
from apex.llm.loader import load_llm_client_from_env
from apex.models import ApexRunToolResult, Mode
from apex.pipeline.code_mode import run_code_mode
from apex.pipeline.helpers import infer_mode_from_prompt, temperatures_for_runs
from apex.pipeline.observability import finalize_run_result
from apex.pipeline.text_mode import run_text_mode


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
) -> ApexRunToolResult:
    run_id = str(uuid.uuid4())
    ensemble_runs_requested = ensemble_runs
    ensemble_runs = (
        ENSEMBLE_RUNS_MIN_EFFECTIVE
        if ensemble_runs < ENSEMBLE_RUNS_MIN_EFFECTIVE
        else min(ENSEMBLE_RUNS_MAX_EFFECTIVE, ensemble_runs)
    )
    inferred = infer_mode_from_prompt(prompt)
    if mode == "auto":
        actual_mode: Literal["text", "code"] = inferred
    else:
        actual_mode = "text" if mode == "text" else "code"

    t_wall_start = time.perf_counter()
    try:
        client = load_llm_client_from_env()
        effective_conventions = load_effective_conventions(repo_conventions=repo_conventions)
        t_total_start = time.perf_counter()
        temps = temperatures_for_runs(ensemble_runs)
        cfg = EnsembleConfig(runs=ensemble_runs, temperatures=temps, max_tokens=max_tokens)

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
            )
        result = _annotate_ensemble_runs_metadata(
            result,
            ensemble_runs_requested=ensemble_runs_requested,
            ensemble_runs_effective=ensemble_runs,
        )
        return finalize_run_result(result, run_id=run_id, mode=actual_mode)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        total_ms = int((time.perf_counter() - t_wall_start) * 1000)
        failed = ApexRunToolResult(
            verdict="blocked",
            output=f"APEX blocked due to extraction/verification failure: {type(e).__name__}",
            adversarial_review=None,
            execution=None,
            metadata={
                "run_id": run_id,
                "mode": actual_mode,
                "mode_request": mode,
                "mode_inferred": inferred if mode == "auto" else None,
                "ensemble_runs_requested": ensemble_runs_requested,
                "ensemble_runs_effective": ensemble_runs,
                "max_tokens": max_tokens,
                "output_mode": output_mode,
                "code_ground_truth": code_ground_truth,
                "ground_truth_enabled": code_ground_truth,
                "error_type": type(e).__name__,
                "error": str(e),
                "timings_ms": {"total": total_ms},
                "pipeline_steps": [],
            },
        )
        return finalize_run_result(failed, run_id=run_id, mode=actual_mode)
