from __future__ import annotations

import time
from typing import Literal

from apex.adversarial_review import review_text
from apex.constants import BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD
from apex.ensemble import EnsembleConfig, generate_text_variants
from apex.models import ApexRunToolResult, TextCompletion
from apex.pipeline.helpers import blocked_code_result, sequence_similarity
from apex.review_pack import build_pr_review_pack
from apex.safety.cot_audit import audit_chain_of_thought
from apex.scoring import DecisionSignals, decide_verdict, select_best_text, text_convergence


async def run_text_mode(
    *,
    client,
    prompt: str,
    cfg: EnsembleConfig,
    ensemble_runs: int,
    max_tokens: int,
    actual_mode: Literal["text", "code"],
    run_id: str,
    t_total_start: float,
    known_good_baseline: str | None,
    language: str | None,
    diff: str | None,
    repo_conventions: str | None,
    output_mode: str,
) -> ApexRunToolResult:
    t_ensemble_start = time.perf_counter()
    variants: list[TextCompletion] = await generate_text_variants(
        client=client, prompt=prompt, config=cfg
    )
    convergence = text_convergence(variants)
    best_i = select_best_text(variants)
    candidate = variants[best_i]
    ensemble_ms = int((time.perf_counter() - t_ensemble_start) * 1000)

    cot_text = candidate.answer + "\n" + "\n".join(candidate.key_claims)
    cot_findings = audit_chain_of_thought(cot_text, context="text")
    if cot_findings:
        return blocked_code_result(
            output="APEX blocked: chain-of-thought leakage detected",
            error="cot_findings=" + ",".join(cot_findings),
            actual_mode=actual_mode,
            ensemble_runs=ensemble_runs,
            code_ground_truth=False,
            run_id=run_id,
            llm_model=client.model,
            timings_ms={
                "ensemble": ensemble_ms,
                "tests": None,
                "adversarial": None,
                "execution": None,
                "total": int((time.perf_counter() - t_total_start) * 1000),
            },
            extra_metadata={"cot_audit": {"detected": True, "findings": cot_findings}},
        )

    t_adv_start = time.perf_counter()
    adversarial = await review_text(
        client=client,
        task_prompt=prompt,
        candidate=candidate,
        max_tokens=min(512, max_tokens),
    )
    adversarial_ms = int((time.perf_counter() - t_adv_start) * 1000)

    high = any(f.severity == "high" for f in adversarial.findings)
    medium = any(f.severity == "medium" for f in adversarial.findings)

    verdict = decide_verdict(
        DecisionSignals(
            convergence=convergence,
            adversarial_high=high,
            adversarial_medium=medium,
            execution_pass=None,
            execution_required=False,
            extraction_ok=True,
        )
    )

    baseline_similarity: float | None = None
    if known_good_baseline is not None:
        baseline_similarity = sequence_similarity(candidate.answer, known_good_baseline)
        if (
            verdict == "high_verified"
            and baseline_similarity < BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD
        ):
            verdict = "needs_review"

    return ApexRunToolResult(
        verdict=verdict,
        output=(
            build_pr_review_pack(
                language=language,
                verdict=verdict,
                prompt=prompt,
                diff=diff,
                repo_conventions=repo_conventions,
                adversarial=adversarial,
                inspection=None,
            )
            if output_mode == "review_pack"
            else candidate.answer
        ),
        adversarial_review=adversarial,
        metadata={
            "mode": actual_mode,
            "ensemble_runs": ensemble_runs,
            "convergence": convergence,
            "run_id": run_id,
            "llm_model": client.model,
            "baseline_similarity": baseline_similarity,
            "output_mode": output_mode,
            "timings_ms": {
                "ensemble": ensemble_ms,
                "adversarial": adversarial_ms,
                "total": int((time.perf_counter() - t_total_start) * 1000),
            },
        },
    )
