from __future__ import annotations

import asyncio
import difflib
import contextlib
import time
import uuid
from typing import Any, Literal

from apex.constants import BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD
from apex.adversarial_review import review_code, review_text
from apex.ensemble import (
    EnsembleConfig,
    generate_code_solution_variants,
    generate_code_tests,
    generate_text_variants,
)
from apex.llm_client import load_llm_client_from_env
from apex.models import (
    ApexRunToolResult,
    CodeSolution,
    CodeTests,
    ExecutionResult,
    Mode,
    TextCompletion,
)
from apex.scoring import (
    DecisionSignals,
    code_convergence,
    decide_verdict,
    select_best_code,
    select_best_text,
    text_convergence,
)

from apex.code_ground_truth.executor_client import (
    ExecutionBackendError,
    ExecutionLimits,
    load_execution_backend_from_env,
)
from apex.inspection_review import inspect_code_doc_only
from apex.safety.cot_audit import audit_chain_of_thought


def infer_mode_from_prompt(prompt: str) -> Literal["text", "code"]:
    p = prompt.lower()
    code_signals = [
        "write code",
        "implement",
        "python",
        "function",
        "class",
        "module",
        "package",
        "tests",
        "pytest",
        "refactor",
    ]
    if any(s in p for s in code_signals):
        return "code"
    return "text"


def _temperatures_for_runs(runs: int) -> tuple[float, ...]:
    if runs <= 2:
        return (0.2, 0.8)
    # runs == 3
    return (0.2, 0.5, 0.9)


def _format_solution(solution: CodeSolution) -> str:
    parts: list[str] = []
    for f in solution.files:
        parts.append(f"# {f.path}\n{f.content}".strip())
    return "\n\n".join(parts).strip()


def validate_code_bundles(solution: CodeSolution, tests: CodeTests) -> None:
    if not any(f.path == "solution.py" for f in solution.files):
        raise ValueError("missing_solution_py")
    if not any(f.path == "test_solution.py" for f in tests.files):
        raise ValueError("missing_test_solution_py")


def _blocked_code_result(
    *,
    output: str,
    error: str,
    actual_mode: Literal["text", "code"],
    ensemble_runs: int,
    code_ground_truth: bool,
    run_id: str,
    llm_model: str,
    timings_ms: dict[str, int | None],
    extra_metadata: dict[str, Any] | None = None,
) -> ApexRunToolResult:
    return ApexRunToolResult(
        verdict="blocked",
        output=output,
        adversarial_review=None,
        execution=None,
        metadata={
            "mode": actual_mode,
            "ensemble_runs": ensemble_runs,
            "ground_truth_enabled": code_ground_truth,
            "run_id": run_id,
            "llm_model": llm_model,
            "error": error,
            "timings_ms": timings_ms,
            **(extra_metadata or {}),
        },
    )


def _normalize_for_similarity(s: str) -> str:
    return " ".join((s or "").split())


def _sequence_similarity(a: str, b: str) -> float:
    a_norm = _normalize_for_similarity(a)
    b_norm = _normalize_for_similarity(b)
    if not a_norm and not b_norm:
        return 1.0
    if not a_norm or not b_norm:
        return 0.0
    return difflib.SequenceMatcher(a=a_norm, b=b_norm).ratio()


async def _run_text_mode(
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
) -> ApexRunToolResult:
    t_ensemble_start = time.perf_counter()
    variants = await generate_text_variants(client=client, prompt=prompt, config=cfg)
    convergence = text_convergence(variants)
    best_i = select_best_text(variants)
    candidate = variants[best_i]
    ensemble_ms = int((time.perf_counter() - t_ensemble_start) * 1000)

    cot_text = candidate.answer + "\n" + "\n".join(candidate.key_claims)
    cot_findings = audit_chain_of_thought(cot_text, context="text")
    if cot_findings:
        return _blocked_code_result(
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
        baseline_similarity = _sequence_similarity(candidate.answer, known_good_baseline)
        # If the candidate diverges strongly from the known-good baseline,
        # downgrade even if ensemble/external signals look strong.
        if verdict == "high_verified" and baseline_similarity < BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD:
            verdict = "needs_review"

    return ApexRunToolResult(
        verdict=verdict,
        output=candidate.answer,
        adversarial_review=adversarial,
        metadata={
            "mode": actual_mode,
            "ensemble_runs": ensemble_runs,
            "convergence": convergence,
            "run_id": run_id,
            "llm_model": client.model,
            "baseline_similarity": baseline_similarity,
            "timings_ms": {
                "ensemble": ensemble_ms,
                "adversarial": adversarial_ms,
                "total": int((time.perf_counter() - t_total_start) * 1000),
            },
        },
    )


async def _run_code_mode(
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
) -> ApexRunToolResult:
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

    cot_code_text = _format_solution(solution)
    cot_findings = audit_chain_of_thought(cot_code_text, context="code")
    if cot_findings:
        return _blocked_code_result(
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
        # If we scheduled tests_v2, cancel it to avoid leaving a pending task
        # around when we return early due to invalid tests_v1.
        if tests_v2_task is not None:
            tests_v2_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await tests_v2_task
        return _blocked_code_result(
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

    tests_files_by_suite = [
        [{"path": f.path, "content": f.content} for f in tests_v1.files]
    ]

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
            return _blocked_code_result(
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
                sum(ms for ms in per_suite_ms if ms is not None)
                if execution_results_any
                else None
            )
            execution = execution_results[0] if execution_results_any else None

    else:
        execution_pass = None

    t_adv_start = time.perf_counter()
    adversarial = await review_code(
        client=client,
        task_prompt=prompt,
        candidate=solution,
        tests_files_by_suite=tests_files_by_suite,
        execution_passes=execution_passes,
        max_tokens=min(512, max_tokens),
    )
    adversarial_ms = int((time.perf_counter() - t_adv_start) * 1000)

    # Inspection is an additional spec-focused review. Policy:
    # - only "high" findings can affect the verdict
    # - medium/low findings are reported in metadata only
    t_ins_start = time.perf_counter()
    inspection = await inspect_code_doc_only(
        client=client,
        task_prompt=prompt,
        candidate=solution,
        tests_files_by_suite=tests_files_by_suite,
        execution_passes=execution_passes,
        max_tokens=min(512, max_tokens),
    )
    inspection_ms = int((time.perf_counter() - t_ins_start) * 1000)

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
            # Principal policy: for code, "high_verified" is only allowed when
            # we actually ran sandbox execution (execution_pass is True).
            execution_required=True,
            extraction_ok=extraction_ok,
        )
    )

    baseline_similarity: float | None = None
    if known_good_baseline is not None:
        baseline_similarity = _sequence_similarity(_format_solution(solution), known_good_baseline)
        if verdict == "high_verified" and baseline_similarity < BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD:
            verdict = "needs_review"

    return ApexRunToolResult(
        verdict=verdict,
        output=_format_solution(solution),
        adversarial_review=adversarial,
        execution=execution,
        metadata={
            "mode": actual_mode,
            "ensemble_runs": ensemble_runs,
            "convergence": convergence,
            "ground_truth_enabled": code_ground_truth,
            "verification_scale": "execution_ground_truth"
            if code_ground_truth
            else "spec_only",
            "run_id": run_id,
            "llm_model": client.model,
            "baseline_similarity": baseline_similarity,
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
        },
    )


async def apex_run(
    *,
    prompt: str,
    mode: Mode = "auto",
    ensemble_runs: int = 3,
    max_tokens: int = 1024,
    code_ground_truth: bool = False,
    known_good_baseline: str | None = None,
) -> ApexRunToolResult:
    run_id = str(uuid.uuid4())
    ensemble_runs = 2 if ensemble_runs < 2 else min(3, ensemble_runs)
    inferred = infer_mode_from_prompt(prompt)
    if mode == "auto":
        actual_mode: Literal["text", "code"] = inferred
    else:
        actual_mode = "text" if mode == "text" else "code"

    client = load_llm_client_from_env()

    extraction_ok = True
    execution: ExecutionResult | None = None
    adversarial = None
    convergence = 0.0

    try:
        t_total_start = time.perf_counter()
        temps = _temperatures_for_runs(ensemble_runs)
        cfg = EnsembleConfig(runs=ensemble_runs, temperatures=temps, max_tokens=max_tokens)

        if actual_mode == "text":
            return await _run_text_mode(
                client=client,
                prompt=prompt,
                cfg=cfg,
                ensemble_runs=ensemble_runs,
                max_tokens=max_tokens,
                actual_mode=actual_mode,
                run_id=run_id,
                t_total_start=t_total_start,
                known_good_baseline=known_good_baseline,
            )

        # code mode (python)
        return await _run_code_mode(
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
        )
    except asyncio.CancelledError:
        # Let structured cancellation propagate cleanly.
        raise
    except Exception as e:
        # Hard fail if we can't even parse/validate the LLM outputs.
        extraction_ok = False
        adversarial = None
        return ApexRunToolResult(
            verdict="blocked",
            output=f"APEX blocked due to extraction/verification failure: {type(e).__name__}",
            adversarial_review=adversarial,
            execution=None,
            metadata={"error": str(e)[:2000], "run_id": run_id},
        )

