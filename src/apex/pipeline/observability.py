"""Finalize tool results: pipeline step validation, ``telemetry``, ``uncertainty``."""

from __future__ import annotations

import secrets
from typing import Any, Literal

from apex.config.constants import (
    CONVERGENCE_MODERATE_THRESHOLD,
    HIGH_VERIFIED_CONVERGENCE_THRESHOLD,
)
from apex.config.contracts import TELEMETRY_SCHEMA_V1, UNCERTAINTY_SCHEMA_V1
from apex.models import ApexRunToolResult, Finding
from apex.pipeline.trace_contract import validate_pipeline_steps

_SEVERITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


def _max_severity_label(findings: list[Finding]) -> Literal["none", "low", "medium", "high"]:
    if not findings:
        return "none"
    best = "none"
    for f in findings:
        sev = f.severity
        if _SEVERITY_RANK[sev] > _SEVERITY_RANK[best]:
            best = sev
    return best  # type: ignore[return-value]


def _inspection_findings_from_metadata(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    ir = metadata.get("inspection_review")
    if not isinstance(ir, dict):
        return []
    raw = ir.get("findings")
    return raw if isinstance(raw, list) else []


def _max_severity_from_raw_findings(
    rows: list[dict[str, Any]],
) -> Literal["none", "low", "medium", "high"]:
    best = "none"
    for r in rows:
        if not isinstance(r, dict):
            continue
        sev = r.get("severity")
        if sev not in _SEVERITY_RANK:
            continue
        if _SEVERITY_RANK[sev] > _SEVERITY_RANK[best]:  # type: ignore[index]
            best = sev
    return best  # type: ignore[return-value]


def _convergence_band(conv: float | None) -> Literal["strong", "moderate", "weak", "unknown"]:
    if conv is None:
        return "unknown"
    if conv >= HIGH_VERIFIED_CONVERGENCE_THRESHOLD:
        return "strong"
    if conv >= CONVERGENCE_MODERATE_THRESHOLD:
        return "moderate"
    return "weak"


def _execution_surface(
    *,
    mode: Literal["text", "code"],
    metadata: dict[str, Any],
) -> Literal["not_applicable", "disabled", "pass", "fail", "inconclusive"]:
    if mode == "text":
        return "not_applicable"
    if not metadata.get("ground_truth_enabled"):
        return "disabled"
    passes = metadata.get("execution_passes")
    if not isinstance(passes, list) or not passes:
        return "inconclusive"
    if any(p is False for p in passes):
        return "fail"
    if all(p is True for p in passes):
        return "pass"
    return "inconclusive"


def build_telemetry_v1(
    *,
    run_id: str,
    metadata: dict[str, Any],
    trace_issues: list[str],
) -> dict[str, Any]:
    """
    OTel-friendly identifiers (W3C-style hex) + one span per pipeline step.
    ``run_wall_ms`` comes from ``metadata.timings_ms.total`` when present.

    ``schema`` is ``TELEMETRY_SCHEMA_V1`` from ``apex.config.contracts``.
    """
    trace_id = secrets.token_hex(16)
    root_span_id = secrets.token_hex(8)
    timings = metadata.get("timings_ms")
    wall: int | None = None
    if isinstance(timings, dict):
        t = timings.get("total")
        if isinstance(t, bool):
            wall = None
        elif isinstance(t, (int, float)):
            wall = round(t)

    steps_raw = metadata.get("pipeline_steps") or []
    spans: list[dict[str, Any]] = []
    if isinstance(steps_raw, list):
        for row in steps_raw:
            if not isinstance(row, dict):
                continue
            sid = row.get("id", "?")
            spans.append(
                {
                    "span_id": secrets.token_hex(8),
                    "parent_span_id": root_span_id,
                    "name": str(sid),
                    "duration_ms": int(row.get("duration_ms", 0))
                    if isinstance(row.get("duration_ms"), int)
                    else 0,
                    "ok": bool(row.get("ok", False)),
                    "detail": row.get("detail") if isinstance(row.get("detail"), dict) else {},
                }
            )

    return {
        "schema": TELEMETRY_SCHEMA_V1,
        "run_id": run_id,
        "trace_id": trace_id,
        "root_span_id": root_span_id,
        "run_wall_ms": wall,
        "spans": spans,
        "trace_validation": {"ok": len(trace_issues) == 0, "issues": trace_issues},
    }


def build_uncertainty_v1(
    result: ApexRunToolResult,
    *,
    mode: Literal["text", "code"],
) -> dict[str, Any]:
    """
    Compact signals for routing / dashboards — derived only from existing result fields.
    """
    md = result.metadata
    conv: float | None = None
    raw_c = md.get("convergence")
    if isinstance(raw_c, (int, float)):
        conv = float(raw_c)

    band = _convergence_band(conv)
    div_hint: float | None = None
    if conv is not None:
        div_hint = max(0.0, min(1.0, 1.0 - conv))

    adv = result.adversarial_review
    if adv is None:
        adv_count = 0
        adv_max: Literal["none", "low", "medium", "high"] = "none"
    else:
        adv_count = len(adv.findings)
        adv_max = _max_severity_label(list(adv.findings))

    raw_insp = _inspection_findings_from_metadata(md)
    insp_max = _max_severity_from_raw_findings(raw_insp)

    return {
        "schema": UNCERTAINTY_SCHEMA_V1,
        "convergence": conv,
        "convergence_band": band,
        "ensemble_divergence_hint": div_hint,
        "adversarial_finding_count": adv_count,
        "adversarial_max_severity": adv_max,
        "code_inspection_finding_count": len(raw_insp) if mode == "code" else None,
        "code_inspection_max_severity": insp_max if mode == "code" else "not_applicable",
        "execution_surface": _execution_surface(mode=mode, metadata=md),
    }


def finalize_run_result(
    result: ApexRunToolResult,
    *,
    run_id: str,
    mode: Literal["text", "code"],
) -> ApexRunToolResult:
    """
    Validate ``pipeline_steps``, attach ``metadata.telemetry`` and ``metadata.uncertainty``.
    """
    md = dict(result.metadata)
    steps = md.get("pipeline_steps")
    issues = validate_pipeline_steps(steps)
    md["telemetry"] = build_telemetry_v1(run_id=run_id, metadata=md, trace_issues=issues)
    md["uncertainty"] = build_uncertainty_v1(result, mode=mode)
    return result.model_copy(update={"metadata": md})
