from __future__ import annotations

import difflib
from typing import Any, Literal

from apex.models import ApexRunToolResult, CodeSolution, CodeTests


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


def temperatures_for_runs(runs: int) -> tuple[float, ...]:
    if runs <= 2:
        return (0.2, 0.8)
    return (0.2, 0.5, 0.9)


def format_solution(solution: CodeSolution) -> str:
    parts: list[str] = []
    for f in solution.files:
        parts.append(f"# {f.path}\n{f.content}".strip())
    return "\n\n".join(parts).strip()


def validate_code_bundles(solution: CodeSolution, tests: CodeTests) -> None:
    if not any(f.path == "solution.py" for f in solution.files):
        raise ValueError("missing_solution_py")
    if not any(f.path == "test_solution.py" for f in tests.files):
        raise ValueError("missing_test_solution_py")


def blocked_run_result(
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
    """Build a ``verdict=blocked`` tool result (text or code mode)."""
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


def sequence_similarity(a: str, b: str) -> float:
    a_norm = _normalize_for_similarity(a)
    b_norm = _normalize_for_similarity(b)
    if not a_norm and not b_norm:
        return 1.0
    if not a_norm or not b_norm:
        return 0.0
    return difflib.SequenceMatcher(a=a_norm, b=b_norm).ratio()
