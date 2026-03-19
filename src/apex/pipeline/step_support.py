from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

StepRequirement = Literal["required", "optional"]

REQUIRED: StepRequirement = "required"
OPTIONAL: StepRequirement = "optional"


@dataclass
class StepTrace:
    """
    Record of one pipeline step execution (for metadata and operator visibility).
    """

    id: str
    requirement: str
    ok: bool
    duration_ms: int
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "requirement": self.requirement,
            "ok": self.ok,
            "duration_ms": self.duration_ms,
            "detail": self.detail,
        }


async def run_async_step(
    step_id: str,
    requirement: StepRequirement,
    work: Callable[[], Awaitable[dict[str, Any]]],
) -> StepTrace:
    """
    Run an async pipeline step with standard timing and error handling.

    Convention for ``work``:
    - Return a dict that MAY include ``ok: bool`` (default True if omitted).
    - Put step-specific payloads in other keys (e.g. ``findings``).

    **required**: exceptions propagate (pipeline aborts upstream).
    **optional**: exceptions become ``ok=False`` with ``detail.error``; no raise.
    """
    t0 = time.perf_counter()
    try:
        result = await work()
        ms = int((time.perf_counter() - t0) * 1000)
        ok = bool(result.get("ok", True))
        detail = {k: v for k, v in result.items() if k != "ok"}
        return StepTrace(
            id=step_id,
            requirement=requirement,
            ok=ok,
            duration_ms=ms,
            detail=detail,
        )
    except Exception as e:
        ms = int((time.perf_counter() - t0) * 1000)
        if requirement == REQUIRED:
            raise
        return StepTrace(
            id=step_id,
            requirement=requirement,
            ok=False,
            duration_ms=ms,
            detail={"error": f"{type(e).__name__}: {e}"},
        )


def skipped_step_record(
    step_id: str,
    requirement: StepRequirement,
    *,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Stable trace for a stage that did not run (e.g. optional suite disabled by config).

    Same shape as ``StepTrace.as_dict()`` so consumers can treat all rows uniformly.
    """
    merged = {"skipped": True, **(detail or {})}
    return StepTrace(
        id=step_id,
        requirement=requirement,
        ok=True,
        duration_ms=0,
        detail=merged,
    ).as_dict()
