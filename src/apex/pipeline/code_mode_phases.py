"""
Code-mode pipeline phases. ``run_code_mode`` orchestrates these in order.

Each phase mutates ``bundle.ctx`` / ``bundle.pipeline_steps`` and returns an
``ApexRunToolResult`` only when the run must end early (blocked).

Collaborators are invoked via ``code_mode_bindings`` (module lookups), not
``from … import``, so tests can monkeypatch ``apex.pipeline.code_mode_bindings``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from apex.code_ground_truth.executor_client import ExecutionBackendError, ExecutionLimits
from apex.config.constants import BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD
from apex.config.policy import FindingsPolicy
from apex.generation.ensemble import EnsembleConfig
from apex.llm.interface import LLMClient
from apex.models import (
    AdversarialReview,
    ApexRunToolResult,
    CodeSolution,
    CodeTests,
    ExecutionResult,
)
from apex.pipeline import code_mode_bindings
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
from apex.review.pack import build_pr_review_pack
from apex.safety.cot_audit import audit_chain_of_thought
from apex.scoring import DecisionSignals

_LOG = logging.getLogger(__name__)


@dataclass
class CodeModeBundle:
    """Mutable working state + immutable inputs for one code-mode run."""

    client: LLMClient
    prompt: str
    cfg: EnsembleConfig
    ensemble_runs: int
    max_tokens: int
    actual_mode: Literal["text", "code"]
    code_ground_truth: bool
    run_id: str
    t_total_start: float
    known_good_baseline: str | None
    language: str | None
    diff: str | None
    repo_conventions: str | None
    output_mode: str
    supplementary_context: str | None
    findings_policy: FindingsPolicy
    ctx: dict[str, Any] = field(default_factory=dict)
    pipeline_steps: list[dict[str, Any]] = field(default_factory=list)
    tests_v2_task: asyncio.Task[CodeTests] | None = None
    tests_v2_start: float | None = None
    extraction_ok: bool = True


async def phase_ensemble(b: CodeModeBundle) -> ApexRunToolResult | None:
    async def _work() -> dict[str, Any]:
        t0 = time.perf_counter()
        solutions: list[CodeSolution] = await code_mode_bindings.generate_code_solution_variants(
            client=b.client, prompt=b.prompt, config=b.cfg
        )
        conv = code_mode_bindings.code_convergence(solutions)
        best_i = code_mode_bindings.select_best_code(solutions)
        solution_local = solutions[best_i]
        ensemble_ms = int((time.perf_counter() - t0) * 1000)
        b.ctx["solution"] = solution_local
        b.ctx["convergence"] = conv
        b.ctx["ensemble_ms"] = ensemble_ms
        return {"ok": True, "convergence": conv}

    trace = await run_async_step("ensemble", REQUIRED, _work)
    b.pipeline_steps.append(trace.as_dict())
    if trace.ok:
        return None
    return blocked_run_result(
        output="APEX blocked: ensemble stage failed",
        error=str(trace.detail),
        actual_mode=b.actual_mode,
        ensemble_runs=b.ensemble_runs,
        code_ground_truth=b.code_ground_truth,
        run_id=b.run_id,
        llm_model=b.client.model,
        timings_ms={
            "ensemble": b.ctx.get("ensemble_ms"),
            "tests": None,
            "adversarial": None,
            "execution": None,
            "total": int((time.perf_counter() - b.t_total_start) * 1000),
        },
        extra_metadata={"pipeline_steps": b.pipeline_steps},
    )


async def phase_cot_audit(
    b: CodeModeBundle,
    *,
    solution: CodeSolution,
    ensemble_ms: int,
) -> ApexRunToolResult | None:
    async def _work() -> dict[str, Any]:
        cot_code_text = format_solution(solution)
        findings = audit_chain_of_thought(cot_code_text, context="code")
        if findings:
            return {"ok": False, "findings": findings}
        return {"ok": True}

    trace = await run_async_step("cot_audit", REQUIRED, _work)
    b.pipeline_steps.append(trace.as_dict())
    if trace.ok:
        return None
    findings = trace.detail.get("findings") or []
    return blocked_run_result(
        output="APEX blocked: chain-of-thought leakage detected",
        error="cot_findings=" + ",".join(str(x) for x in findings),
        actual_mode=b.actual_mode,
        ensemble_runs=b.ensemble_runs,
        code_ground_truth=b.code_ground_truth,
        run_id=b.run_id,
        llm_model=b.client.model,
        timings_ms={
            "ensemble": ensemble_ms,
            "tests": None,
            "adversarial": None,
            "execution": None,
            "total": int((time.perf_counter() - b.t_total_start) * 1000),
        },
        extra_metadata={
            "cot_audit": {"detected": True, "findings": findings},
            "pipeline_steps": b.pipeline_steps,
        },
    )


async def phase_test_generation_v1(
    b: CodeModeBundle,
    *,
    solution: CodeSolution,
    ensemble_ms: int,
) -> ApexRunToolResult | None:
    async def _work() -> dict[str, Any]:
        if b.code_ground_truth:
            b.tests_v2_start = time.perf_counter()
            b.tests_v2_task = asyncio.create_task(
                code_mode_bindings.generate_code_tests(
                    client=b.client,
                    prompt=b.prompt,
                    config=b.cfg,
                    suite_label="tests_v2",
                    temperature=0.5,
                )
            )
        t0 = time.perf_counter()
        tests_v1 = await code_mode_bindings.generate_code_tests(
            client=b.client,
            prompt=b.prompt,
            config=b.cfg,
            suite_label="tests_v1",
            temperature=0.2,
        )
        tests_v1_ms = int((time.perf_counter() - t0) * 1000)
        b.ctx["tests_v1"] = tests_v1
        b.ctx["tests_v1_ms"] = tests_v1_ms
        try:
            validate_code_bundles(solution, tests_v1)
        except ValueError as ve:
            if b.tests_v2_task is not None:
                b.tests_v2_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await b.tests_v2_task
            return {"ok": False, "error": str(ve)}
        return {"ok": True}

    trace = await run_async_step("test_generation_v1", REQUIRED, _work)
    b.pipeline_steps.append(trace.as_dict())
    if trace.ok:
        return None
    b.extraction_ok = False
    return blocked_run_result(
        output=f"APEX blocked: {trace.detail.get('error', 'test_generation_v1')}",
        error=str(trace.detail.get("error", "")),
        actual_mode=b.actual_mode,
        ensemble_runs=b.ensemble_runs,
        code_ground_truth=b.code_ground_truth,
        run_id=b.run_id,
        llm_model=b.client.model,
        timings_ms={
            "ensemble": ensemble_ms,
            "tests": b.ctx.get("tests_v1_ms"),
            "adversarial": None,
            "execution": None,
            "total": int((time.perf_counter() - b.t_total_start) * 1000),
        },
        extra_metadata={"pipeline_steps": b.pipeline_steps},
    )


async def phase_test_generation_v2_and_execution(
    b: CodeModeBundle,
    *,
    solution: CodeSolution,
    tests_v1: CodeTests,
    tests_v1_ms: int,
    ensemble_ms: int,
) -> ApexRunToolResult | None:
    tests_files_by_suite: list[list[dict[str, str]]] = [
        [{"path": f.path, "content": f.content} for f in tests_v1.files]
    ]
    execution_passes: list[bool | None] | None = None
    execution_pass: bool | None = None
    execution_ms: int | None = None
    execution_ms_per_suite: list[int | None] | None = None
    tests_ms_per_suite: list[int] | None = None
    execution: ExecutionResult | None = None

    if b.code_ground_truth:

        async def _tg2() -> dict[str, Any]:
            if b.tests_v2_task is None or b.tests_v2_start is None:
                raise RuntimeError("Internal error: tests_v2 not scheduled")
            tests_v2 = await b.tests_v2_task
            tests_v2_ms = int((time.perf_counter() - b.tests_v2_start) * 1000)
            b.ctx["tests_v2"] = tests_v2
            b.ctx["tests_v2_ms"] = tests_v2_ms
            try:
                validate_code_bundles(solution, tests_v2)
            except ValueError as ve:
                return {"ok": False, "error": str(ve)}
            return {"ok": True}

        tg2 = await run_async_step("test_generation_v2", REQUIRED, _tg2)
        b.pipeline_steps.append(tg2.as_dict())
        if not tg2.ok:
            b.extraction_ok = False
            return blocked_run_result(
                output=f"APEX blocked: {tg2.detail.get('error', 'test_generation_v2')}",
                error=str(tg2.detail.get("error", "")),
                actual_mode=b.actual_mode,
                ensemble_runs=b.ensemble_runs,
                code_ground_truth=b.code_ground_truth,
                run_id=b.run_id,
                llm_model=b.client.model,
                timings_ms={
                    "ensemble": ensemble_ms,
                    "tests": tests_v1_ms + int(b.ctx.get("tests_v2_ms") or 0),
                    "adversarial": None,
                    "execution": None,
                    "total": int((time.perf_counter() - b.t_total_start) * 1000),
                },
                extra_metadata={"pipeline_steps": b.pipeline_steps},
            )

        tests_v2: CodeTests = b.ctx["tests_v2"]
        tests_v2_ms: int = b.ctx["tests_v2_ms"]
        tests_files_by_suite.append(
            [{"path": f.path, "content": f.content} for f in tests_v2.files]
        )
        tests_ms_per_suite = [tests_v1_ms, tests_v2_ms]

        async def _execution_backend() -> dict[str, Any]:
            try:
                backend = code_mode_bindings.load_execution_backend_from_env()
            except ExecutionBackendError:
                b.ctx["execution_passes"] = [None, None]
                b.ctx["execution_pass"] = None
                b.ctx["execution_ms"] = None
                b.ctx["execution_ms_per_suite"] = None
                b.ctx["execution"] = None
                return {"ok": True, "backend": "unavailable", "execution_pass": None}

            async def _exec_suite(
                suite_idx: int, suite_tests: CodeTests
            ) -> tuple[bool | None, int | None, ExecutionResult | None]:
                t_exec_start = time.perf_counter()
                try:
                    exec_result = await backend.execute(
                        run_id=f"{b.run_id}-suite{suite_idx}",
                        solution=solution,
                        tests=suite_tests,
                        limits=ExecutionLimits(),
                    )
                    ms = int((time.perf_counter() - t_exec_start) * 1000)
                    return exec_result.pass_, ms, exec_result
                except ExecutionBackendError as ebe:
                    errs = b.ctx.setdefault("execution_suite_errors", [])
                    errs.append(
                        {
                            "suite": suite_idx,
                            "reason": ebe.reason,
                            "http_status": ebe.http_status,
                            "message": str(ebe)[:512],
                        }
                    )
                    return None, None, None
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    _LOG.warning(
                        "execution backend suite %s raised %s",
                        suite_idx,
                        type(exc).__name__,
                        exc_info=True,
                    )
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
            b.ctx["execution_passes"] = per_suite_passes
            b.ctx["execution_pass"] = ep
            b.ctx["execution_ms_per_suite"] = per_suite_ms
            b.ctx["execution_ms"] = execution_ms_local
            b.ctx["execution"] = execution_results[0] if execution_results_any else None
            return {
                "ok": True,
                "execution_pass": ep,
                "execution_ms": execution_ms_local,
            }

        ex = await run_async_step("execution_backend", OPTIONAL, _execution_backend)
        b.pipeline_steps.append(ex.as_dict())
        execution_passes = b.ctx.get("execution_passes")
        execution_pass = b.ctx.get("execution_pass")
        execution_ms = b.ctx.get("execution_ms")
        execution_ms_per_suite = b.ctx.get("execution_ms_per_suite")
        execution = b.ctx.get("execution")
    else:
        b.pipeline_steps.append(
            skipped_step_record(
                "test_generation_v2",
                OPTIONAL,
                detail={"reason": "code_ground_truth_disabled"},
            )
        )
        b.pipeline_steps.append(
            skipped_step_record(
                "execution_backend",
                OPTIONAL,
                detail={"reason": "code_ground_truth_disabled"},
            )
        )
        execution_pass = None

    b.ctx["_review_execution_passes"] = execution_passes
    b.ctx["_review_execution_pass"] = execution_pass
    b.ctx["_review_execution_ms"] = execution_ms
    b.ctx["_review_execution_ms_per_suite"] = execution_ms_per_suite
    b.ctx["_review_tests_ms_per_suite"] = tests_ms_per_suite
    b.ctx["_review_tests_files_by_suite"] = tests_files_by_suite
    b.ctx["_review_execution_result"] = execution
    return None


async def phase_reviews_findings_verdict_and_pack(
    b: CodeModeBundle,
    *,
    solution: CodeSolution,
    ensemble_ms: int,
    tests_v1_ms: int,
    convergence: float,
) -> ApexRunToolResult:
    execution_passes = b.ctx.get("_review_execution_passes")
    execution_pass = b.ctx.get("_review_execution_pass")
    execution_ms = b.ctx.get("_review_execution_ms")
    execution_ms_per_suite = b.ctx.get("_review_execution_ms_per_suite")
    tests_ms_per_suite = b.ctx.get("_review_tests_ms_per_suite")
    tests_files_by_suite = b.ctx.get("_review_tests_files_by_suite")
    execution = b.ctx.get("_review_execution_result")
    policy = b.findings_policy

    async def _run_adversarial_review() -> tuple[AdversarialReview, int]:
        t_adv_start = time.perf_counter()
        review = await code_mode_bindings.review_code(
            client=b.client,
            task_prompt=b.prompt,
            candidate=solution,
            tests_files_by_suite=tests_files_by_suite,
            execution_passes=execution_passes,
            max_tokens=min(512, b.max_tokens),
        )
        return review, int((time.perf_counter() - t_adv_start) * 1000)

    async def _run_code_inspection() -> tuple[AdversarialReview, int]:
        t_ins_start = time.perf_counter()
        review = await code_mode_bindings.inspect_code_doc_only(
            client=b.client,
            task_prompt=b.prompt,
            candidate=solution,
            tests_files_by_suite=tests_files_by_suite,
            execution_passes=execution_passes,
            max_tokens=min(512, b.max_tokens),
            language=b.language,
            diff=b.diff,
            repo_conventions=b.repo_conventions,
            supplementary_context=b.supplementary_context,
        )
        return review, int((time.perf_counter() - t_ins_start) * 1000)

    (adv_raw, adversarial_ms), (ins_raw, inspection_ms) = await asyncio.gather(
        _run_adversarial_review(),
        _run_code_inspection(),
    )

    b.pipeline_steps.append(
        StepTrace(
            id="adversarial_review",
            requirement=REQUIRED,
            ok=True,
            duration_ms=adversarial_ms,
            detail={"finding_count_pre_policy": len(adv_raw.findings)},
        ).as_dict()
    )
    b.pipeline_steps.append(
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

    async def _apply_findings_policy() -> dict[str, Any]:
        nonlocal adversarial, inspection
        adversarial = policy.apply(adv_raw)
        inspection = policy.apply(ins_raw)
        assert adversarial is not None and inspection is not None
        return {
            "ok": True,
            "adversarial_findings_post_policy": len(adversarial.findings),
            "inspection_findings_post_policy": len(inspection.findings),
        }

    fp_step = await run_async_step("findings_policy", OPTIONAL, _apply_findings_policy)
    b.pipeline_steps.append(fp_step.as_dict())
    if not fp_step.ok or adversarial is None or inspection is None:
        return blocked_run_result(
            output="APEX blocked: findings policy stage failed",
            error=str(fp_step.detail),
            actual_mode=b.actual_mode,
            ensemble_runs=b.ensemble_runs,
            code_ground_truth=b.code_ground_truth,
            run_id=b.run_id,
            llm_model=b.client.model,
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
                "total": int((time.perf_counter() - b.t_total_start) * 1000),
            },
            extra_metadata={"pipeline_steps": b.pipeline_steps},
        )

    high = any(f.severity == "high" for f in adversarial.findings)
    medium = any(f.severity == "medium" for f in adversarial.findings)
    inspection_high = any(f.severity == "high" for f in inspection.findings)
    high = high or inspection_high

    verdict = code_mode_bindings.decide_verdict(
        DecisionSignals(
            convergence=convergence,
            adversarial_high=high,
            adversarial_medium=medium,
            execution_pass=execution_pass,
            execution_required=True,
            extraction_ok=b.extraction_ok,
        )
    )

    baseline_similarity: float | None = None
    if b.known_good_baseline is not None:

        async def _baseline_alignment() -> dict[str, Any]:
            nonlocal verdict
            sim = sequence_similarity(format_solution(solution), b.known_good_baseline)
            downgraded = False
            if verdict == "high_verified" and sim < BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD:
                verdict = "needs_review"
                downgraded = True
            b.ctx["baseline_similarity"] = sim
            return {"ok": True, "similarity": sim, "downgraded": downgraded}

        bl = await run_async_step("baseline_alignment", OPTIONAL, _baseline_alignment)
        b.pipeline_steps.append(bl.as_dict())
        baseline_similarity = b.ctx.get("baseline_similarity")
    else:
        b.pipeline_steps.append(
            skipped_step_record(
                "baseline_alignment",
                OPTIONAL,
                detail={"reason": "known_good_baseline_not_set"},
            )
        )

    meta: dict[str, Any] = {
        "mode": b.actual_mode,
        "ensemble_runs": b.ensemble_runs,
        "convergence": convergence,
        "ground_truth_enabled": b.code_ground_truth,
        "verification_scale": "execution_ground_truth" if b.code_ground_truth else "spec_only",
        "run_id": b.run_id,
        "llm_model": b.client.model,
        "baseline_similarity": baseline_similarity,
        "output_mode": b.output_mode,
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
            "total": int((time.perf_counter() - b.t_total_start) * 1000),
        },
        "execution_passes": execution_passes,
        "tests_ms_per_suite": tests_ms_per_suite,
        "execution_ms_per_suite": execution_ms_per_suite,
        "inspection_review": inspection.model_dump(),
        "language": b.language,
        "pipeline_steps": b.pipeline_steps,
    }
    if b.ctx.get("execution_suite_errors"):
        meta["execution_suite_errors"] = b.ctx["execution_suite_errors"]

    return ApexRunToolResult(
        verdict=verdict,
        output=(
            build_pr_review_pack(
                language=b.language,
                verdict=verdict,
                prompt=b.prompt,
                diff=b.diff,
                repo_conventions=b.repo_conventions,
                adversarial=adversarial,
                inspection=inspection,
            )
            if b.output_mode == "review_pack"
            else format_solution(solution)
        ),
        adversarial_review=adversarial,
        execution=execution,
        metadata=meta,
    )
