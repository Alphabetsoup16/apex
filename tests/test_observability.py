from __future__ import annotations

from apex.models import AdversarialReview, ApexRunToolResult, Finding
from apex.pipeline.observability import (
    build_telemetry_v1,
    build_uncertainty_v1,
    finalize_run_result,
)
from apex.pipeline.trace_contract import validate_pipeline_steps


def test_validate_pipeline_steps_accepts_well_formed_rows() -> None:
    steps = [
        {
            "id": "a",
            "requirement": "required",
            "ok": True,
            "duration_ms": 1,
            "detail": {},
        }
    ]
    assert validate_pipeline_steps(steps) == []


def test_validate_pipeline_steps_reports_gaps() -> None:
    assert validate_pipeline_steps({}) == ["pipeline_steps must be a list"]
    assert validate_pipeline_steps([{"id": "x"}]) != []


def test_finalize_attaches_telemetry_and_uncertainty() -> None:
    result = ApexRunToolResult(
        verdict="needs_review",
        output="x",
        adversarial_review=AdversarialReview(
            findings=[Finding(severity="low", type="t", confidence=0.1, evidence="e")]
        ),
        metadata={
            "convergence": 0.5,
            "pipeline_steps": [
                {
                    "id": "ensemble",
                    "requirement": "required",
                    "ok": True,
                    "duration_ms": 10,
                    "detail": {},
                }
            ],
            "timings_ms": {"total": 99},
            "mode": "text",
        },
    )
    out = finalize_run_result(result, run_id="rid", mode="text")
    assert out.metadata["telemetry"]["schema"] == "apex.telemetry/v1"
    assert out.metadata["telemetry"]["run_id"] == "rid"
    assert len(out.metadata["telemetry"]["spans"]) == 1
    assert out.metadata["telemetry"]["trace_validation"]["ok"] is True
    u = out.metadata["uncertainty"]
    assert u["schema"] == "apex.uncertainty/v1"
    assert u["convergence_band"] == "weak"
    assert u["execution_surface"] == "not_applicable"
    assert u["adversarial_finding_count"] == 1


def test_uncertainty_code_execution_surface_disabled() -> None:
    r = ApexRunToolResult(
        verdict="needs_review",
        output="",
        metadata={"ground_truth_enabled": False, "mode": "code"},
    )
    u = build_uncertainty_v1(r, mode="code")
    assert u["execution_surface"] == "disabled"


def test_telemetry_lists_validation_issues() -> None:
    md = {"pipeline_steps": [{"id": "only"}]}
    tel = build_telemetry_v1(run_id="r", metadata=md, trace_issues=["bad"])
    assert tel["trace_validation"]["ok"] is False
    assert tel["trace_validation"]["issues"] == ["bad"]


def test_telemetry_run_wall_accepts_numeric_total() -> None:
    md = {"timings_ms": {"total": 100.7}}
    tel = build_telemetry_v1(run_id="r", metadata=md, trace_issues=[])
    assert tel["run_wall_ms"] == 101


def test_validate_pipeline_steps_rejects_bad_requirement() -> None:
    bad = [
        {
            "id": "x",
            "requirement": "maybe",
            "ok": True,
            "duration_ms": 0,
            "detail": {},
        }
    ]
    issues = validate_pipeline_steps(bad)
    assert any("requirement" in i for i in issues)
