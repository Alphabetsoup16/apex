"""Frozen snapshot of inputs + resolved mode for one ``apex_run`` (guards + pipeline)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from apex.models import Mode
from apex.pipeline.guard_metadata import blocked_run_base_metadata, clamp_ensemble_runs
from apex.pipeline.helpers import infer_mode_from_prompt


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


@dataclass(frozen=True)
class ApexRunContext:
    """Everything guard paths and the text/code pipeline need for one invocation."""

    run_id: str
    mode: Mode
    actual_mode: Literal["text", "code"]
    inferred: Literal["text", "code"]
    ensemble_runs_requested: int
    ensemble_runs_effective: int
    max_tokens: int
    code_ground_truth: bool
    known_good_baseline: str | None
    language: str | None
    diff: str | None
    repo_conventions: str | None
    output_mode: str
    supplementary_context: str | None
    prompt: str

    def blocked_base_metadata(self, timings_total_ms: int = 0) -> dict[str, object]:
        """Shared ``metadata`` keys for blocked results (aligned with MCP preflight)."""
        return blocked_run_base_metadata(
            run_id=self.run_id,
            actual_mode=self.actual_mode,
            mode=self.mode,
            inferred=self.inferred,
            ensemble_runs_requested=self.ensemble_runs_requested,
            ensemble_runs_effective=self.ensemble_runs_effective,
            max_tokens=self.max_tokens,
            output_mode=self.output_mode,
            code_ground_truth=self.code_ground_truth,
            timings_total_ms=timings_total_ms,
        )


def build_apex_run_context(
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
) -> ApexRunContext:
    ens_req, ens_eff = clamp_ensemble_runs(ensemble_runs)
    actual_mode, inferred = resolve_run_modes(prompt=prompt, mode=mode)
    return ApexRunContext(
        run_id=run_id or str(uuid.uuid4()),
        mode=mode,
        actual_mode=actual_mode,
        inferred=inferred,
        ensemble_runs_requested=ens_req,
        ensemble_runs_effective=ens_eff,
        max_tokens=max_tokens,
        code_ground_truth=code_ground_truth,
        known_good_baseline=known_good_baseline,
        language=language,
        diff=diff,
        repo_conventions=repo_conventions,
        output_mode=output_mode,
        supplementary_context=supplementary_context,
        prompt=prompt,
    )
