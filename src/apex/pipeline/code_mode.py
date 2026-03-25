from __future__ import annotations

from typing import Literal

from apex.config.policy import FindingsPolicy
from apex.generation.ensemble import EnsembleConfig
from apex.llm.interface import LLMClient
from apex.models import ApexRunToolResult
from apex.pipeline.code_mode_phases import (
    CodeModeBundle,
    phase_cot_audit,
    phase_ensemble,
    phase_reviews_findings_verdict_and_pack,
    phase_test_generation_v1,
    phase_test_generation_v2_and_execution,
)


async def run_code_mode(
    *,
    client: LLMClient,
    prompt: str,
    cfg: EnsembleConfig,
    ensemble_runs: int,
    max_tokens: int,
    actual_mode: Literal["text", "code"],
    code_ground_truth: bool,
    run_id: str,
    t_total_start: float,
    known_good_baseline: str | None,
    language: str | None,
    diff: str | None,
    repo_conventions: str | None,
    output_mode: str,
    supplementary_context: str | None = None,
    findings_policy: FindingsPolicy | None = None,
) -> ApexRunToolResult:
    if findings_policy is None:
        raise ValueError("findings_policy is required for run_code_mode")

    bundle = CodeModeBundle(
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
        repo_conventions=repo_conventions,
        output_mode=output_mode,
        supplementary_context=supplementary_context,
        findings_policy=findings_policy,
    )

    if early := await phase_ensemble(bundle):
        return early

    solution = bundle.ctx["solution"]
    convergence = bundle.ctx["convergence"]
    ensemble_ms: int = bundle.ctx["ensemble_ms"]

    if early := await phase_cot_audit(bundle, solution=solution, ensemble_ms=ensemble_ms):
        return early

    if early := await phase_test_generation_v1(bundle, solution=solution, ensemble_ms=ensemble_ms):
        return early

    tests_v1 = bundle.ctx["tests_v1"]
    tests_v1_ms: int = bundle.ctx["tests_v1_ms"]

    if early := await phase_test_generation_v2_and_execution(
        bundle,
        solution=solution,
        tests_v1=tests_v1,
        tests_v1_ms=tests_v1_ms,
        ensemble_ms=ensemble_ms,
    ):
        return early

    return await phase_reviews_findings_verdict_and_pack(
        bundle,
        solution=solution,
        ensemble_ms=ensemble_ms,
        tests_v1_ms=tests_v1_ms,
        convergence=convergence,
    )
