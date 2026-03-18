from __future__ import annotations

import time
import uuid
from typing import Literal

from apex.adversarial_review import review_code, review_text
from apex.ensemble import (
    EnsembleConfig,
    generate_code_solution_variants,
    generate_code_tests,
    generate_text_variants,
)
from apex.llm_client import AnthropicMessagesClient, load_anthropic_config_from_env
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


async def apex_run(
    *,
    prompt: str,
    mode: Mode = "auto",
    ensemble_runs: int = 3,
    max_tokens: int = 1024,
    code_ground_truth: bool = False,
) -> ApexRunToolResult:
    run_id = str(uuid.uuid4())
    ensemble_runs = 2 if ensemble_runs < 2 else min(3, ensemble_runs)
    inferred = infer_mode_from_prompt(prompt)
    if mode == "auto":
        actual_mode: Literal["text", "code"] = inferred
    else:
        actual_mode = "text" if mode == "text" else "code"

    llm_cfg = load_anthropic_config_from_env()
    client = AnthropicMessagesClient(llm_cfg)

    extraction_ok = True
    execution: ExecutionResult | None = None
    adversarial = None
    convergence = 0.0

    try:
        t_total_start = time.perf_counter()
        temps = _temperatures_for_runs(ensemble_runs)
        cfg = EnsembleConfig(runs=ensemble_runs, temperatures=temps, max_tokens=max_tokens)

        if actual_mode == "text":
            t_ensemble_start = time.perf_counter()
            variants = await generate_text_variants(client=client, prompt=prompt, config=cfg)
            convergence = text_convergence(variants)
            best_i = select_best_text(variants)
            candidate = variants[best_i]
            ensemble_ms = int((time.perf_counter() - t_ensemble_start) * 1000)

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
                    extraction_ok=extraction_ok,
                )
            )
            output = candidate.answer
            return ApexRunToolResult(
                verdict=verdict, output=output, adversarial_review=adversarial, metadata={
                    "mode": actual_mode,
                    "ensemble_runs": ensemble_runs,
                    "convergence": convergence,
                    "run_id": run_id,
                    "llm_model": llm_cfg.model,
                    "timings_ms": {
                        "ensemble": ensemble_ms,
                        "adversarial": adversarial_ms,
                        "total": int((time.perf_counter() - t_total_start) * 1000),
                    },
                }
            )

        # code mode (python)
        t_ensemble_start = time.perf_counter()
        solutions: list[CodeSolution] = await generate_code_solution_variants(
            client=client, prompt=prompt, config=cfg
        )
        convergence = code_convergence(solutions)
        best_i = select_best_code(solutions)
        solution = solutions[best_i]
        ensemble_ms = int((time.perf_counter() - t_ensemble_start) * 1000)

        t_tests_start = time.perf_counter()
        tests = await generate_code_tests(client=client, prompt=prompt, config=cfg)
        tests_ms = int((time.perf_counter() - t_tests_start) * 1000)

        try:
            validate_code_bundles(solution, tests)
        except ValueError as ve:
            extraction_ok = False
            return ApexRunToolResult(
                verdict="blocked",
                output=f"APEX blocked: {ve}",
                adversarial_review=None,
                execution=None,
                metadata={
                    "mode": actual_mode,
                    "ensemble_runs": ensemble_runs,
                    "ground_truth_enabled": code_ground_truth,
                    "run_id": run_id,
                    "llm_model": llm_cfg.model,
                    "error": str(ve),
                    "timings_ms": {
                        "ensemble": ensemble_ms,
                        "tests": tests_ms,
                        "adversarial": None,
                        "execution": None,
                        "total": int((time.perf_counter() - t_total_start) * 1000),
                    },
                },
            )

        execution_pass: bool | None = None
        execution_ms: int | None = None
        if code_ground_truth:
            try:
                backend = load_execution_backend_from_env()
                t_exec_start = time.perf_counter()
                execution = await backend.execute(
                    run_id=run_id,
                    solution=solution,
                    tests=tests,
                    limits=ExecutionLimits(),
                )
                execution_pass = execution.pass_
                execution_ms = int((time.perf_counter() - t_exec_start) * 1000)
            except ExecutionBackendError:
                execution_pass = None
            except Exception:
                execution_pass = False

        t_adv_start = time.perf_counter()
        adversarial = await review_code(
            client=client,
            task_prompt=prompt,
            candidate=solution,
            tests_files=[{"path": f.path, "content": f.content} for f in tests.files],
            execution_pass=execution_pass,
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
                execution_pass=execution_pass,
                # Principal policy: for code, "high_verified" is only allowed when
                # we actually ran sandbox execution (execution_pass is True).
                # If execution is disabled, execution_pass stays None, which forces
                # the verdict to downgrade to `needs_review`.
                execution_required=True,
                extraction_ok=extraction_ok,
            )
        )

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
                "verification_scale": "execution_ground_truth" if code_ground_truth else "spec_only",
                "run_id": run_id,
                "llm_model": llm_cfg.model,
                "timings_ms": {
                    "ensemble": ensemble_ms,
                    "tests": tests_ms,
                    "adversarial": adversarial_ms,
                    "execution": execution_ms,
                    "total": int((time.perf_counter() - t_total_start) * 1000),
                },
            },
        )
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

