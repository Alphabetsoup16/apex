from __future__ import annotations

from dataclasses import dataclass

from apex.pipeline.step_support import OPTIONAL, REQUIRED, StepRequirement


@dataclass(frozen=True)
class PipelineStepSpec:
    """
    Declarative description of a pipeline stage (documentation + discoverability).

    Implementation still lives in ``text_mode`` / ``code_mode``; keep this catalog
    aligned when you add or change behavior.
    """

    id: str
    requirement: StepRequirement
    modes: tuple[str, ...]
    summary: str
    verdict_impact: str


TEXT_PIPELINE_STEPS: tuple[PipelineStepSpec, ...] = (
    PipelineStepSpec(
        id="ensemble",
        requirement=REQUIRED,
        modes=("text",),
        summary="Multi-path LLM generation; convergence scoring uses all variants.",
        verdict_impact="Failure aborts run (extraction/LLM).",
    ),
    PipelineStepSpec(
        id="cot_audit",
        requirement=REQUIRED,
        modes=("text",),
        summary="Heuristic check for chain-of-thought leakage in answer + claims.",
        verdict_impact="Blocks run if leakage detected.",
    ),
    PipelineStepSpec(
        id="adversarial_review",
        requirement=REQUIRED,
        modes=("text",),
        summary="Structured adversarial pass over the selected candidate.",
        verdict_impact="High severity blocks; medium affects high_verified.",
    ),
    PipelineStepSpec(
        id="baseline_alignment",
        requirement=OPTIONAL,
        modes=("text",),
        summary="Runs only when ``known_good_baseline`` is set.",
        verdict_impact="May downgrade high_verified → needs_review.",
    ),
)

CODE_PIPELINE_STEPS: tuple[PipelineStepSpec, ...] = (
    PipelineStepSpec(
        id="ensemble",
        requirement=REQUIRED,
        modes=("code",),
        summary="Multi-path code generation; structural convergence across variants.",
        verdict_impact="Failure aborts run (extraction/LLM).",
    ),
    PipelineStepSpec(
        id="cot_audit",
        requirement=REQUIRED,
        modes=("code",),
        summary="Heuristic CoT leakage check on formatted solution.",
        verdict_impact="Blocks run if leakage detected.",
    ),
    PipelineStepSpec(
        id="test_generation_v1",
        requirement=REQUIRED,
        modes=("code",),
        summary="First independent pytest suite (always generated).",
        verdict_impact="Bundle validation failure blocks.",
    ),
    PipelineStepSpec(
        id="test_generation_v2",
        requirement=OPTIONAL,
        modes=("code",),
        summary="Second suite only when ``code_ground_truth`` is enabled.",
        verdict_impact="Enables dual-suite execution ladder.",
    ),
    PipelineStepSpec(
        id="execution_backend",
        requirement=OPTIONAL,
        modes=("code",),
        summary="Sandbox execution when ground truth on; missing backend → inconclusive passes.",
        verdict_impact="Required for high_verified in code mode when enabled.",
    ),
    PipelineStepSpec(
        id="adversarial_review",
        requirement=REQUIRED,
        modes=("code",),
        summary="Structured adversarial review (tests + execution context).",
        verdict_impact="High severity blocks; medium affects high_verified.",
    ),
    PipelineStepSpec(
        id="doc_inspection",
        requirement=OPTIONAL,
        modes=("code",),
        summary="LLM doc-only inspection (diff-first when diff provided).",
        verdict_impact="Only **high** findings affect verdict; medium/low are report-only.",
    ),
    PipelineStepSpec(
        id="findings_policy",
        requirement=OPTIONAL,
        modes=("code",),
        summary="Optional filter on finding types/severities (global + repo policy files).",
        verdict_impact="Reporting only; does not weaken safety blocks.",
    ),
    PipelineStepSpec(
        id="baseline_alignment",
        requirement=OPTIONAL,
        modes=("code",),
        summary="Runs when ``known_good_baseline`` is set.",
        verdict_impact="May downgrade high_verified → needs_review.",
    ),
)


def catalog_summary() -> dict[str, list[dict[str, str]]]:
    """Compact JSON-friendly summary for metadata or debugging."""

    def rows(steps: tuple[PipelineStepSpec, ...]) -> list[dict[str, str]]:
        return [
            {
                "id": s.id,
                "requirement": s.requirement,
                "summary": s.summary,
                "verdict_impact": s.verdict_impact,
            }
            for s in steps
        ]

    return {"text": rows(TEXT_PIPELINE_STEPS), "code": rows(CODE_PIPELINE_STEPS)}
