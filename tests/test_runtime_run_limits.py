from __future__ import annotations

import asyncio

import pytest

import apex.pipeline.run as pipeline_run
import apex.pipeline.text_mode as text_mode
from apex.models import AdversarialReview, TextCompletion
from apex.pipeline.top_level_errors import APEX_CAPACITY, APEX_RUN_TIMEOUT


class _FakeClient:
    def __init__(self) -> None:
        self.model = "fake-limits"


def test_concurrency_gate_try_acquire_and_release() -> None:
    from apex.runtime.run_limits import ConcurrencyGate

    async def main() -> None:
        g = ConcurrencyGate(2)
        assert await g.try_acquire() is True
        assert await g.try_acquire() is True
        assert await g.try_acquire() is False
        await g.release()
        assert await g.try_acquire() is True
        await g.release()
        await g.release()

    asyncio.run(main())


def test_load_run_limit_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from apex.runtime.run_limits import load_run_limit_settings

    monkeypatch.delenv("APEX_MAX_CONCURRENT_RUNS", raising=False)
    monkeypatch.delenv("APEX_RUN_MAX_WALL_MS", raising=False)
    s = load_run_limit_settings()
    assert s.max_concurrent == 0 and s.wall_ms == 0


def test_apex_run_capacity_rejects_when_limit_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APEX_MAX_CONCURRENT_RUNS", "1")
    monkeypatch.delenv("APEX_RUN_MAX_WALL_MS", raising=False)

    barrier = asyncio.Event()
    resume = asyncio.Event()

    async def slow_run_text(**kwargs):
        barrier.set()
        await resume.wait()
        raise AssertionError("unreachable after cancel")

    monkeypatch.setattr(pipeline_run, "load_llm_client_from_env", lambda: _FakeClient())
    monkeypatch.setattr(pipeline_run, "run_text_mode", slow_run_text)

    async def main() -> None:
        t1 = asyncio.create_task(
            pipeline_run.apex_run(prompt="a", mode="text", ensemble_runs=2, max_tokens=32)
        )
        await asyncio.wait_for(barrier.wait(), timeout=2.0)
        r2 = await pipeline_run.apex_run(prompt="b", mode="text", ensemble_runs=2, max_tokens=32)
        assert r2.verdict == "blocked"
        assert r2.metadata.get("error_code") == APEX_CAPACITY
        assert r2.metadata.get("capacity_limit") == 1
        t1.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t1

    asyncio.run(main())


def test_apex_run_wall_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APEX_RUN_MAX_WALL_MS", "80")
    monkeypatch.delenv("APEX_MAX_CONCURRENT_RUNS", raising=False)

    async def slow_gen(*, client, prompt: str, config):
        await asyncio.sleep(0.3)
        return [
            TextCompletion(answer="A", key_claims=["x"]),
            TextCompletion(answer="B", key_claims=["y"]),
        ]

    async def fake_review_text(*, client, task_prompt: str, candidate, max_tokens: int):
        return AdversarialReview(findings=[])

    monkeypatch.setattr(pipeline_run, "load_llm_client_from_env", lambda: _FakeClient())
    monkeypatch.setattr(text_mode, "generate_text_variants", slow_gen)
    monkeypatch.setattr(text_mode, "review_text", fake_review_text)
    monkeypatch.setattr(text_mode, "text_convergence", lambda variants: 0.5)
    monkeypatch.setattr(text_mode, "select_best_text", lambda variants: 0)
    monkeypatch.setattr(text_mode, "decide_verdict", lambda signals: "needs_review")

    result = asyncio.run(
        pipeline_run.apex_run(prompt="hello", mode="text", ensemble_runs=2, max_tokens=64)
    )
    assert result.verdict == "blocked"
    assert result.metadata.get("error_code") == APEX_RUN_TIMEOUT
    assert result.metadata.get("run_wall_timeout_ms") == 80


def test_apex_sanitized_error_new_codes() -> None:
    from apex.pipeline.top_level_errors import APEX_INTERNAL, apex_sanitized_error

    assert "concurrent" in apex_sanitized_error(APEX_CAPACITY).lower()
    assert "time" in apex_sanitized_error(APEX_RUN_TIMEOUT).lower()
    assert apex_sanitized_error("apex.unknown_code") == apex_sanitized_error(APEX_INTERNAL)
