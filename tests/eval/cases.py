"""
Declarative regression fixtures for pipeline behavior (no live LLM).

Cases assert verdict and ordered ``metadata.pipeline_steps`` ids so refactors
that change control flow fail loudly in CI.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegressionCase:
    """Single end-to-end expectation for ``apex.pipeline.run.apex_run``."""

    name: str
    mode: str
    code_ground_truth: bool
    expect_verdict: str
    expect_step_ids: tuple[str, ...]
    known_good_baseline: str | None = None
    prompt: str = "hello"
    findings_ignore_types: tuple[str, ...] = ()
    findings_ignore_severities: tuple[str, ...] = ()


TEXT_STANDARD = RegressionCase(
    name="text_standard",
    mode="text",
    code_ground_truth=False,
    expect_verdict="needs_review",
    expect_step_ids=(
        "ensemble",
        "cot_audit",
        "adversarial_review",
        "baseline_alignment",
    ),
)

TEXT_COT_BLOCKED = RegressionCase(
    name="text_cot_blocked",
    mode="text",
    code_ground_truth=False,
    expect_verdict="blocked",
    expect_step_ids=("ensemble", "cot_audit"),
    prompt="hello",
)

CODE_SPEC_ONLY = RegressionCase(
    name="code_spec_only",
    mode="code",
    code_ground_truth=False,
    expect_verdict="needs_review",
    expect_step_ids=(
        "ensemble",
        "cot_audit",
        "test_generation_v1",
        "test_generation_v2",
        "execution_backend",
        "adversarial_review",
        "doc_inspection",
        "findings_policy",
        "baseline_alignment",
    ),
    prompt="write code: implement f",
)

CODE_SPEC_POLICY_EXTRAS = RegressionCase(
    name="code_spec_policy_extras",
    mode="code",
    code_ground_truth=False,
    expect_verdict="needs_review",
    expect_step_ids=CODE_SPEC_ONLY.expect_step_ids,
    prompt="write code: implement f",
    findings_ignore_types=("unused_type",),
    findings_ignore_severities=("info",),
)

ALL_CASES: tuple[RegressionCase, ...] = (
    TEXT_STANDARD,
    TEXT_COT_BLOCKED,
    CODE_SPEC_ONLY,
    CODE_SPEC_POLICY_EXTRAS,
)
