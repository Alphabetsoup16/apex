from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any, Literal

from apex.code_ground_truth.executor_client import (
    ExecutionBackendError,
    ExecutionLimits,
    load_execution_backend_from_env,
)
from apex.config.constants import BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD
from apex.config.policy import load_findings_policy
from apex.generation.ensemble import (
    EnsembleConfig,
    generate_code_solution_variants,
    generate_code_tests,
)
from apex.llm.interface import LLMClient
from apex.models import (
    AdversarialReview,
    ApexRunToolResult,
    CodeSolution,
    CodeTests,
    ExecutionResult,
)
from apex.pipeline.helpers import (
    blocked_run_result,
    format_solution,
    sequence_similarity,
    validate_code_bundles,
)
from apex.pipeline.step_support import (
    OPTIONAL,
    REQUIRED,
    StepTrace,
    run_async_step,
    skipped_step_record,
)
from apex.review.adversarial import review_code
from apex.review.inspection import inspect_code_doc_only
from apex.review.pack import build_pr_review_pack
from apex.safety.cot_audit import audit_chain_of_thought
from apex.scoring import DecisionSignals, code_convergence, decide_verdict, select_best_code


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
) -> ApexRunToolResult:
    findings_policy = load_findings_policy()
    extraction_ok = True
    execution: ExecutionResult | None = None
    convergence = 0.0
    pipeline_steps: list[dict[str, Any]] = []
    ctx: dict[str, Any] = {}
    tests_v2_task: asyncio.Task[CodeTests] | None = None
    tests_v2_start: float | None = None

    async def _ensemble() -> dict[str, Any]:
        t0 = time.perf_counter()
        solutions: list[CodeSolution] = await generate_code_solution_variants(
            client=client, prompt=prompt, config=cfg
        )
        convergence_local = code_convergence(solutions)
        best_i = select_best_code(solutions)
        solution_local = solutions[best_i]
        ensemble_ms = int((time.perf_counter() - t0) * 1000)
        ctx["solution"] = solution_local
        ctx["convergence"] = convergence_local
        ctx["ensemble_ms"] = ensemble_ms
        return {"ok": True, "convergence": convergence_local}

    ens = await run_async_step("ensemble", REQUIRED, _ensemble)
    pipeline_steps.append(ens.as_dict())
    if not ens.ok:
        return blocked_run_result(
            output="APEX blocked: ensemble stage failed",
            error=str(ens.detail),
            actual_mode=actual_mode,
            ensemble_runs=ensemble_runs,
            code_ground_truth=code_ground_truth,
            run_id=run_id,
            llm_model=client.model,
            timings_ms={
                "ensemble": ctx.get("ensemble_ms"),
                "tests": None,
                "adversarial": None,
                "execution": None,
                "total": int((time.perf_counter() - t_total_start) * 1000),
            },
            extra_metadata={"pipeline_steps": pipeline_steps},
        )

    solution: CodeSolution = ctx["solution"]
    convergence = ctx["convergence"]
    ensemble_ms: int = ctx["ensemble_ms"]

    async def _cot_audit() -> dict[str, Any]:
        cot_code_text = format_solution(solution)
        findings = audit_chain_of_thought(cot_code_text, context="code")
        if findings:
            return {"ok": False, "findings": findings}
        return {"ok": True}

    cot_trace = await run_async_step("cot_audit", REQUIRED, _cot_audit)
    pipeline_steps.append(cot_trace.as_dict())
    if not cot_trace.ok:
        findings = cot_trace.detail.get("findings") or []
        return blocked_run_result(
            output="APEX blocked: chain-of-thought leakage detected",
            error="cot_findings=" + ",".join(str(x) for x in findings),
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
            extra_metadata={
                "cot_audit": {"detected": True, "findings": findings},
                "pipeline_steps": pipeline_steps,
            },
        )

    async def _test_generation_v1() -> dict[str, Any]:
        nonlocal tests_v2_task, tests_v2_start
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
        t0 = time.perf_counter()
        tests_v1 = await generate_code_tests(
            client=client,
            prompt=prompt,
            config=cfg,
            suite_label="tests_v1",
            temperature=0.2,
        )
        tests_v1_ms = int((time.perf_counter() - t0) * 1000)
        ctx["tests_v1"] = tests_v1
        ctx["tests_v1_ms"] = tests_v1_ms
        try:
            validate_code_bundles(solution, tests_v1)
        except ValueError as ve:
            if tests_v2_task is not None:
                tests_v2_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await tests_v2_task
            return {"ok": False, "error": str(ve)}
        return {"ok": True}

    tg1 = await run_async_step("test_generation_v1", REQUIRED, _test_generation_v1)
    pipeline_steps.append(tg1.as_dict())
    if not tg1.ok:
        extraction_ok = False
        return blocked_run_result(
            output=f"APEX blocked: {tg1.detail.get('error', 'test_generation_v1')}",
            error=str(tg1.detail.get("error", "")),
            actual_mode=actual_mode,
            ensemble_runs=ensemble_runs,
            code_ground_truth=code_ground_truth,
            run_id=run_id,
            llm_model=client.model,
            timings_ms={
                "ensemble": ensemble_ms,
                "tests": ctx.get("tests_v1_ms"),
                "adversarial": None,
                "execution": None,
                "total": int((time.perf_counter() - t_total_start) * 1000),
            },
            extra_metadata={"pipeline_steps": pipeline_steps},
        )

    tests_v1: CodeTests = ctx["tests_v1"]
    tests_v1_ms: int = ctx["tests_v1_ms"]
    tests_files_by_suite: list[list[dict[str, str]]] = [
        [{"path": f.path, "content": f.content} for f in tests_v1.files]
    ]

    execution_passes: list[bool | None] | None = None
    execution_pass: bool | None = None
    execution_ms: int | None = None
    execution_ms_per_suite: list[int | None] | None = None
    tests_ms_per_suite: list[int] | None = None

    if code_ground_truth:

        async def _test_generation_v2() -> dict[str, Any]:
            if tests_v2_task is None or tests_v2_start is None:
                raise RuntimeError("Internal error: tests_v2 not scheduled")
            tests_v2 = await tests_v2_task
            tests_v2_ms = int((time.perf_counter() - tests_v2_start) * 1000)
            ctx["tests_v2"] = tests_v2
            ctx["tests_v2_ms"] = tests_v2_ms
            try:
                validate_code_bundles(solution, tests_v2)
            except ValueError as ve:
                return {"ok": False, "error": str(ve)}
            return {"ok": True}

        tg2 = await run_async_step("test_generation_v2", REQUIRED, _test_generation_v2)
        pipeline_steps.append(tg2.as_dict())
        if not tg2.ok:
            extraction_ok = False
            return blocked_run_result(
                output=f"APEX blocked: {tg2.detail.get('error', 'test_generation_v2')}",
                error=str(tg2.detail.get("error", "")),
                actual_mode=actual_mode,
                ensemble_runs=ensemble_runs,
                code_ground_truth=code_ground_truth,
                run_id=run_id,
                llm_model=client.model,
                timings_ms={
                    "ensemble": ensemble_ms,
                    "tests": tests_v1_ms + int(ctx.get("tests_v2_ms") or 0),
                    "adversarial": None,
                    "execution": None,
                    "total": int((time.perf_counter() - t_total_start) * 1000),
                },
                extra_metadata={"pipeline_steps": pipeline_steps},
            )

        tests_v2: CodeTests = ctx["tests_v2"]
        tests_v2_ms: int = ctx["tests_v2_ms"]
        tests_files_by_suite.append(
            [{"path": f.path, "content": f.content} for f in tests_v2.files]
        )
        tests_ms_per_suite = [tests_v1_ms, tests_v2_ms]

        async def _execution_backend() -> dict[str, Any]:
            try:
                backend = load_execution_backend_from_env()
            except ExecutionBackendError:
                ctx["execution_passes"] = [None, None]
                ctx["execution_pass"] = None
                ctx["execution_ms"] = None
                ctx["execution_ms_per_suite"] = None
                ctx["execution"] = None
                return {"ok": True, "backend": "unavailable", "execution_pass": None}

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

            ep = (
                False
                if any(p is False for p in per_suite_passes)
                else True
                if all(p is True for p in per_suite_passes)
                else None
            )
            execution_results_any = any(r is not None for r in execution_results)
            execution_ms_local = (
                sum(ms for ms in per_suite_ms if ms is not None) if execution_results_any else None
            )
            ctx["execution_passes"] = per_suite_passes
            ctx["execution_pass"] = ep
            ctx["execution_ms_per_suite"] = per_suite_ms
            ctx["execution_ms"] = execution_ms_local
            ctx["execution"] = execution_results[0] if execution_results_any else None
            return {
                "ok": True,
                "execution_pass": ep,
                "execution_ms": execution_ms_local,
            }

        ex = await run_async_step("execution_backend", OPTIONAL, _execution_backend)
        pipeline_steps.append(ex.as_dict())
        execution_passes = ctx.get("execution_passes")
        execution_pass = ctx.get("execution_pass")
        execution_ms = ctx.get("execution_ms")
        execution_ms_per_suite = ctx.get("execution_ms_per_suite")
        execution = ctx.get("execution")
    else:
        pipeline_steps.append(
            skipped_step_record(
                "test_generation_v2",
                OPTIONAL,
                detail={"reason": "code_ground_truth_disabled"},
            )
        )
        pipeline_steps.append(
            skipped_step_record(
                "execution_backend",
                OPTIONAL,
                detail={"reason": "code_ground_truth_disabled"},
            )
        )
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
                supplementary_context=supplementary_context,
            )
            return review, int((time.perf_counter() - t_ins_start) * 1000)
        except asyncio.CancelledError:
            raise

    (adv_raw, adversarial_ms), (ins_raw, inspection_ms) = await asyncio.gather(
        _run_adversarial_review(),
        _run_code_inspection(),
    )

    pipeline_steps.append(
        StepTrace(
            id="adversarial_review",
            requirement=REQUIRED,
            ok=True,
            duration_ms=adversarial_ms,
            detail={"finding_count_pre_policy": len(adv_raw.findings)},
        ).as_dict()
    )
    pipeline_steps.append(
        StepTrace(
            id="doc_inspection",
            requirement=OPTIONAL,
            ok=True,
            duration_ms=inspection_ms,
            detail={"finding_count_pre_policy": len(ins_raw.findings)},
        ).as_dict()
    )

    adversarial: AdversarialReview | None = None
    inspection: AdversarialReview | None = None

    async def _findings_policy() -> dict[str, Any]:
        nonlocal adversarial, inspection
        adversarial = findings_policy.apply(adv_raw)
        inspection = findings_policy.apply(ins_raw)
        assert adversarial is not None and inspection is not None
        return {
            "ok": True,
            "adversarial_findings_post_policy": len(adversarial.findings),
            "inspection_findings_post_policy": len(inspection.findings),
        }

    fp = await run_async_step("findings_policy", OPTIONAL, _findings_policy)
    pipeline_steps.append(fp.as_dict())
    if not fp.ok or adversarial is None or inspection is None:
        return blocked_run_result(
            output="APEX blocked: findings policy stage failed",
            error=str(fp.detail),
            actual_mode=actual_mode,
            ensemble_runs=ensemble_runs,
            code_ground_truth=code_ground_truth,
            run_id=run_id,
            llm_model=client.model,
            timings_ms={
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
            extra_metadata={"pipeline_steps": pipeline_steps},
        )

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

        async def _baseline_alignment() -> dict[str, Any]:
            nonlocal verdict
            sim = sequence_similarity(format_solution(solution), known_good_baseline)
            downgraded = False
            if verdict == "high_verified" and sim < BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD:
                verdict = "needs_review"
                downgraded = True
            ctx["baseline_similarity"] = sim
            return {"ok": True, "similarity": sim, "downgraded": downgraded}

        bl = await run_async_step("baseline_alignment", OPTIONAL, _baseline_alignment)
        pipeline_steps.append(bl.as_dict())
        baseline_similarity = ctx.get("baseline_similarity")
    else:
        pipeline_steps.append(
            skipped_step_record(
                "baseline_alignment",
                OPTIONAL,
                detail={"reason": "known_good_baseline_not_set"},
            )
        )

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
            "pipeline_steps": pipeline_steps,
        },
    )
