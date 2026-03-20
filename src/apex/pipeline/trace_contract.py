from __future__ import annotations

from typing import Any, TypedDict

# Every row in ``metadata.pipeline_steps`` must expose these keys (``detail`` may be empty).
PIPELINE_STEP_REQUIRED_KEYS: frozenset[str] = frozenset(
    {"id", "requirement", "ok", "duration_ms", "detail"}
)


class PipelineStepTraceDict(TypedDict):
    """Contract for one element of ``metadata.pipeline_steps`` (JSON-serializable)."""

    id: str
    requirement: str
    ok: bool
    duration_ms: int
    detail: dict[str, Any]


def validate_pipeline_steps(steps: Any) -> list[str]:
    """
    Return human-readable issues; empty list means the list matches the contract.

    Does not raise — callers attach issues to telemetry for operators / strict CI.
    """
    issues: list[str] = []
    if not isinstance(steps, list):
        return ["pipeline_steps must be a list"]

    for i, row in enumerate(steps):
        prefix = f"pipeline_steps[{i}]"
        if not isinstance(row, dict):
            issues.append(f"{prefix} must be an object")
            continue
        missing = PIPELINE_STEP_REQUIRED_KEYS - row.keys()
        if missing:
            issues.append(f"{prefix} missing keys: {sorted(missing)}")
        if "detail" in row and not isinstance(row.get("detail"), dict):
            issues.append(f"{prefix}.detail must be an object")
        if "duration_ms" in row and not isinstance(row.get("duration_ms"), int):
            issues.append(f"{prefix}.duration_ms must be an integer")
        if "ok" in row and not isinstance(row.get("ok"), bool):
            issues.append(f"{prefix}.ok must be a boolean")
        if "id" in row and not isinstance(row.get("id"), str):
            issues.append(f"{prefix}.id must be a string")
        if "requirement" in row:
            req = row.get("requirement")
            if req not in ("required", "optional"):
                issues.append(f"{prefix}.requirement must be 'required' or 'optional'")
    return issues
