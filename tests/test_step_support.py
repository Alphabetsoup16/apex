from __future__ import annotations

import asyncio

import pytest

from apex.pipeline.step_support import OPTIONAL, REQUIRED, run_async_step
from apex.pipeline.steps_catalog import catalog_summary


def test_run_async_step_ok_default() -> None:
    async def work() -> dict:
        return {}

    trace = asyncio.run(run_async_step("s", REQUIRED, work))
    assert trace.ok is True
    assert trace.id == "s"
    assert trace.requirement == REQUIRED
    assert trace.duration_ms >= 0


def test_run_async_step_ok_explicit_false() -> None:
    async def work() -> dict:
        return {"ok": False, "reason": "nope"}

    trace = asyncio.run(run_async_step("s", REQUIRED, work))
    assert trace.ok is False
    assert trace.detail.get("reason") == "nope"


def test_optional_step_swallows_exception() -> None:
    async def work() -> dict:
        raise ValueError("flaky")

    trace = asyncio.run(run_async_step("s", OPTIONAL, work))
    assert trace.ok is False
    assert trace.detail.get("error_type") == "ValueError"
    assert trace.detail.get("message") == "optional_step_failed"
    assert "flaky" not in str(trace.detail)


def test_required_step_reraises() -> None:
    async def work() -> dict:
        raise ValueError("fatal")

    with pytest.raises(ValueError, match="fatal"):
        asyncio.run(run_async_step("s", REQUIRED, work))


def test_catalog_summary_shape() -> None:
    summary = catalog_summary()
    assert "text" in summary and "code" in summary
    assert summary["text"] and summary["code"]
    assert all("id" in row and "requirement" in row for row in summary["text"])


def test_step_trace_as_dict() -> None:
    async def work() -> dict:
        return {"ok": True, "x": 1}

    trace = asyncio.run(run_async_step("s", REQUIRED, work))
    d = trace.as_dict()
    assert d["id"] == "s"
    assert d["ok"] is True
    assert d["detail"] == {"x": 1}
