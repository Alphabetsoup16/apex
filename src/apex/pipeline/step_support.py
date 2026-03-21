from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from apex.observability.progress_events import (
    STEP_END,
    STEP_START,
    current_progress_run_id,
    emit_progress,
)

StepRequirement = Literal["required", "optional"]

REQUIRED: StepRequirement = "required"
OPTIONAL: StepRequirement = "optional"

_LOG = logging.getLogger(__name__)


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
    **optional**: exceptions become ``ok=False`` with ``detail.error_type`` only (no raw
    ``str(exc)`` — avoids leaking provider text into traces / ledger detail).
    """
    rid = current_progress_run_id()
    if rid:
        emit_progress(STEP_START, step_id=step_id, requirement=requirement, run_id=rid)

    t0 = time.perf_counter()
    try:
        result = await work()
        ms = int((time.perf_counter() - t0) * 1000)
        ok = bool(result.get("ok", True))
        detail = {k: v for k, v in result.items() if k != "ok"}
        trace = StepTrace(
            id=step_id,
            requirement=requirement,
            ok=ok,
            duration_ms=ms,
            detail=detail,
        )
        if rid:
            emit_progress(
                STEP_END,
                step_id=step_id,
                requirement=requirement,
                ok=trace.ok,
                duration_ms=trace.duration_ms,
                run_id=rid,
            )
        return trace
    except Exception as e:
        ms = int((time.perf_counter() - t0) * 1000)
        if rid:
            emit_progress(
                STEP_END,
                step_id=step_id,
                requirement=requirement,
                ok=False,
                duration_ms=ms,
                run_id=rid,
                error_type=type(e).__name__,
            )
        if requirement == REQUIRED:
            raise
        _LOG.debug(
            "optional step %r failed: %s",
            step_id,
            type(e).__name__,
            exc_info=True,
        )
        return StepTrace(
            id=step_id,
            requirement=requirement,
            ok=False,
            duration_ms=ms,
            detail={
                "error_type": type(e).__name__,
                "message": "optional_step_failed",
            },
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
    See ``apex.pipeline.trace_contract`` for the stable JSON shape (``PipelineStepTraceDict``).
    """
    merged = {"skipped": True, **(detail or {})}
    return StepTrace(
        id=step_id,
        requirement=requirement,
        ok=True,
        duration_ms=0,
        detail=merged,
    ).as_dict()
