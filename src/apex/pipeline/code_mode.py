from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Literal

from apex.adversarial_review import review_code
from apex.code_ground_truth.executor_client import (
    ExecutionBackendError,
    ExecutionLimits,
    load_execution_backend_from_env,
)
from apex.constants import BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD
from apex.ensemble import (
    EnsembleConfig,
    generate_code_solution_variants,
    generate_code_tests,
)
from apex.inspection_review import inspect_code_doc_only
from apex.models import (
    AdversarialReview,
    ApexRunToolResult,
    CodeSolution,
    CodeTests,
    ExecutionResult,
)
from apex.pipeline.helpers import (
    blocked_code_result,
    format_solution,
    sequence_similarity,
    validate_code_bundles,
)
from apex.policy import load_findings_policy
from apex.review_pack import build_pr_review_pack
from apex.safety.cot_audit import audit_chain_of_thought
from apex.scoring import DecisionSignals, code_convergence, decide_verdict, select_best_code


async def run_code_mode(
    *,
    client,
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
) -> ApexRunToolResult:
    findings_policy = load_findings_policy()
    extraction_ok = True
    execution: ExecutionResult | None = None
    adversarial = None
    convergence = 0.0

    t_ensemble_start = time.perf_counter()
    solutions: list[CodeSolution] = await generate_code_solution_variants(
        client=client, prompt=prompt, config=cfg
    )
    convergence = code_convergence(solutions)
    best_i = select_best_code(solutions)
    solution = solutions[best_i]
    ensemble_ms = int((time.perf_counter() - t_ensemble_start) * 1000)

    cot_code_text = format_solution(solution)
    cot_findings = audit_chain_of_thought(cot_code_text, context="code")
    if cot_findings:
        return blocked_code_result(
            output="APEX blocked: chain-of-thought leakage detected",
            error="cot_findings=" + ",".join(cot_findings),
            actual_mode=actual_mode,
            ensemble_runs=ensemble_runs,
            code_ground_truth=code_ground_truth,
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

    tests_v2_task = None
    tests_v2_start = None
    if code_ground_truth:
        tests_v2_start = time.perf_counter()
        tests_v2_task = asyncio.create_task(
            generate_code_tests(
                client=client,
                prompt=prompt,
                config=cfg,
                suite_label="tests_v2",
                temperature=0.5,
            )
        )

    t_tests_start = time.perf_counter()
    tests_v1 = await generate_code_tests(
        client=client,
        prompt=prompt,
        config=cfg,
        suite_label="tests_v1",
        temperature=0.2,
    )
    tests_v1_ms = int((time.perf_counter() - t_tests_start) * 1000)

    try:
        validate_code_bundles(solution, tests_v1)
    except ValueError as ve:
        extraction_ok = False
        if tests_v2_task is not None:
            tests_v2_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await tests_v2_task
        return blocked_code_result(
            output=f"APEX blocked: {ve}",
            error=str(ve),
            actual_mode=actual_mode,
            ensemble_runs=ensemble_runs,
            code_ground_truth=code_ground_truth,
            run_id=run_id,
            llm_model=client.model,
            timings_ms={
                "ensemble": ensemble_ms,
                "tests": tests_v1_ms,
                "adversarial": None,
                "execution": None,
                "total": int((time.perf_counter() - t_total_start) * 1000),
            },
        )

    tests_files_by_suite = [[{"path": f.path, "content": f.content} for f in tests_v1.files]]

    execution_passes: list[bool | None] | None = None
    execution_pass: bool | None = None
    execution_ms: int | None = None
    execution_ms_per_suite: list[int | None] | None = None
    tests_ms_per_suite: list[int] | None = None

    if code_ground_truth:
        if tests_v2_task is None or tests_v2_start is None:
            raise RuntimeError("Internal error: tests_v2 not scheduled")
        tests_v2 = await tests_v2_task
        tests_v2_ms = int((time.perf_counter() - tests_v2_start) * 1000)

        try:
            validate_code_bundles(solution, tests_v2)
        except ValueError as ve:
            extraction_ok = False
            return blocked_code_result(
                output=f"APEX blocked: {ve}",
                error=str(ve),
                actual_mode=actual_mode,
                ensemble_runs=ensemble_runs,
                code_ground_truth=code_ground_truth,
                run_id=run_id,
                llm_model=client.model,
                timings_ms={
                    "ensemble": ensemble_ms,
                    "tests": tests_v1_ms + tests_v2_ms,
                    "adversarial": None,
                    "execution": None,
                    "total": int((time.perf_counter() - t_total_start) * 1000),
                },
            )

        tests_files_by_suite.append(
            [{"path": f.path, "content": f.content} for f in tests_v2.files]
        )
        tests_ms_per_suite = [tests_v1_ms, tests_v2_ms]

        try:
            backend = load_execution_backend_from_env()
        except ExecutionBackendError:
            execution_passes = [None, None]
            execution_pass = None
        else:

            async def _exec_suite(
                suite_idx: int, suite_tests: CodeTests
            ) -> tuple[bool | None, int | None, ExecutionResult | None]:
                t_exec_start = time.perf_counter()
                try:
                    exec_result = await backend.execute(
                        run_id=f"{run_id}-suite{suite_idx}",
                        solution=solution,
                        tests=suite_tests,
                        limits=ExecutionLimits(),
                    )
                    ms = int((time.perf_counter() - t_exec_start) * 1000)
                    return exec_result.pass_, ms, exec_result
                except ExecutionBackendError:
                    return None, None, None
                except asyncio.CancelledError:
                    raise
                except Exception:
                    return False, None, None

            exec_tasks = [
                asyncio.create_task(_exec_suite(0, tests_v1)),
                asyncio.create_task(_exec_suite(1, tests_v2)),
            ]
            exec_results: list[
                tuple[bool | None, int | None, ExecutionResult | None]
            ] = await asyncio.gather(*exec_tasks)

            per_suite_passes = [r[0] for r in exec_results]
            per_suite_ms = [r[1] for r in exec_results]
            execution_results = [r[2] for r in exec_results]

            execution_passes = per_suite_passes
            execution_pass = (
                False
                if any(p is False for p in per_suite_passes)
                else True
                if all(p is True for p in per_suite_passes)
                else None
            )

            execution_ms_per_suite = per_suite_ms
            execution_results_any = any(r is not None for r in execution_results)
            execution_ms = (
                sum(ms for ms in per_suite_ms if ms is not None) if execution_results_any else None
            )
            execution = execution_results[0] if execution_results_any else None

    else:
        execution_pass = None

    async def _run_adversarial_review() -> tuple[AdversarialReview, int]:
        t_adv_start = time.perf_counter()
        try:
            review = await review_code(
                client=client,
                task_prompt=prompt,
                candidate=solution,
                tests_files_by_suite=tests_files_by_suite,
                execution_passes=execution_passes,
                max_tokens=min(512, max_tokens),
            )
            return review, int((time.perf_counter() - t_adv_start) * 1000)
        except asyncio.CancelledError:
            raise

    async def _run_code_inspection() -> tuple[AdversarialReview, int]:
        t_ins_start = time.perf_counter()
        try:
            review = await inspect_code_doc_only(
                client=client,
                task_prompt=prompt,
                candidate=solution,
                tests_files_by_suite=tests_files_by_suite,
                execution_passes=execution_passes,
                max_tokens=min(512, max_tokens),
                language=language,
                diff=diff,
                repo_conventions=repo_conventions,
            )
            return review, int((time.perf_counter() - t_ins_start) * 1000)
        except asyncio.CancelledError:
            raise

    (adversarial, adversarial_ms), (inspection, inspection_ms) = await asyncio.gather(
        _run_adversarial_review(),
        _run_code_inspection(),
    )
    adversarial = findings_policy.apply(adversarial)
    inspection = findings_policy.apply(inspection)

    high = any(f.severity == "high" for f in adversarial.findings)
    medium = any(f.severity == "medium" for f in adversarial.findings)
    inspection_high = any(f.severity == "high" for f in inspection.findings)
    high = high or inspection_high

    verdict = decide_verdict(
        DecisionSignals(
            convergence=convergence,
            adversarial_high=high,
            adversarial_medium=medium,
            execution_pass=execution_pass,
            execution_required=True,
            extraction_ok=extraction_ok,
        )
    )

    baseline_similarity: float | None = None
    if known_good_baseline is not None:
        baseline_similarity = sequence_similarity(format_solution(solution), known_good_baseline)
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
                inspection=inspection,
            )
            if output_mode == "review_pack"
            else format_solution(solution)
        ),
        adversarial_review=adversarial,
        execution=execution,
        metadata={
            "mode": actual_mode,
            "ensemble_runs": ensemble_runs,
            "convergence": convergence,
            "ground_truth_enabled": code_ground_truth,
            "verification_scale": "execution_ground_truth" if code_ground_truth else "spec_only",
            "run_id": run_id,
            "llm_model": client.model,
            "baseline_similarity": baseline_similarity,
            "output_mode": output_mode,
            "timings_ms": {
                "ensemble": ensemble_ms,
                "tests": (
                    (tests_ms_per_suite[0] + tests_ms_per_suite[1])
                    if tests_ms_per_suite is not None
                    else tests_v1_ms
                ),
                "adversarial": adversarial_ms,
                "inspection": inspection_ms,
                "execution": execution_ms,
                "total": int((time.perf_counter() - t_total_start) * 1000),
            },
            "execution_passes": execution_passes,
            "tests_ms_per_suite": tests_ms_per_suite,
            "execution_ms_per_suite": execution_ms_per_suite,
            "inspection_review": inspection.model_dump(),
            "language": language,
        },
    )
