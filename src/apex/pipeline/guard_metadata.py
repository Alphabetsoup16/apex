"""Shared metadata for runs that never entered the text/code pipeline (guard / MCP preflight)."""

from __future__ import annotations

from typing import Literal

from apex.config.constants import ENSEMBLE_RUNS_MAX_EFFECTIVE, ENSEMBLE_RUNS_MIN_EFFECTIVE
from apex.models import Mode


def clamp_ensemble_runs(requested: int) -> tuple[int, int]:
    """
    Return ``(requested, effective)`` ensemble counts — same clamp as ``apex_run``.
    """
    eff = (
        ENSEMBLE_RUNS_MIN_EFFECTIVE
        if requested < ENSEMBLE_RUNS_MIN_EFFECTIVE
        else min(ENSEMBLE_RUNS_MAX_EFFECTIVE, requested)
    )
    return requested, eff


def blocked_run_base_metadata(
    *,
    run_id: str,
    actual_mode: Literal["text", "code"],
    mode: Mode,
    inferred: Literal["text", "code"],
    ensemble_runs_requested: int,
    ensemble_runs_effective: int,
    max_tokens: int,
    output_mode: str,
    code_ground_truth: bool,
    timings_total_ms: int,
) -> dict[str, object]:
    """Keys aligned with ``apex_run`` guard-path blocked results (telemetry / clients)."""
    return {
        "run_id": run_id,
        "mode": actual_mode,
        "mode_request": mode,
        "mode_inferred": inferred if mode == "auto" else None,
        "ensemble_runs_requested": ensemble_runs_requested,
        "ensemble_runs_effective": ensemble_runs_effective,
        "max_tokens": max_tokens,
        "output_mode": output_mode,
        "ground_truth_enabled": code_ground_truth,
        "pipeline_steps": [],
        "timings_ms": {"total": timings_total_ms},
    }
