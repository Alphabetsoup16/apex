import asyncio

import pytest

from apex.code_ground_truth.executor_client import ExecutionBackendError
from apex.models import (
    AdversarialReview,
    ApexRunToolResult,
    CodeFile,
    CodeSolution,
    CodeTests,
    ExecutionResult,
    Finding,
    TextCompletion,
)
from apex import orchestrator


class _FakeClient:
    def __init__(self, model: str) -> None:
        self.model = model


def _solution_bundle() -> CodeSolution:
    return CodeSolution(files=[CodeFile(path="solution.py", content="def f():\n    return 1\n")])


def _tests_bundle(v: int) -> CodeTests:
    # Both suites must use `test_solution.py` for validate_code_bundles.
    return CodeTests(
        files=[CodeFile(path="test_solution.py", content=f"def test_v(v={v}):\n    assert True\n")],
        test_framework="pytest",
    )


def test_apex_run_text_mode_uses_review_and_sets_signals(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(orchestrator, "load_llm_client_from_env", lambda: _FakeClient("fake-text"))

    async def fake_generate_text_variants(*, client, prompt: str, config):
        assert client.model == "fake-text"
        assert prompt == "hello"
        assert hasattr(config, "runs")
        return [
            TextCompletion(answer="A", key_claims=["x"]),
            TextCompletion(answer="B", key_claims=["y"]),
        ]

    async def fake_review_text(*, client, task_prompt: str, candidate, max_tokens: int):
        assert task_prompt == "hello"
        assert candidate.answer in ("A", "B")
        assert max_tokens > 0
        return AdversarialReview(
            findings=[Finding(severity="low", type="t", confidence=0.1, evidence="e")]
        )

    monkeypatch.setattr(orchestrator, "generate_text_variants", fake_generate_text_variants)
    monkeypatch.setattr(orchestrator, "review_text", fake_review_text)
    monkeypatch.setattr(orchestrator, "text_convergence", lambda variants: 0.5)
    monkeypatch.setattr(orchestrator, "select_best_text", lambda variants: 0)

    captured = {}

    def fake_decide_verdict(signals):
        captured["signals"] = signals
        return "needs_review"

    monkeypatch.setattr(orchestrator, "decide_verdict", fake_decide_verdict)

    result = asyncio.run(
        orchestrator.apex_run(
            prompt="hello",
            mode="text",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=False,
        )
    )
    assert isinstance(result, ApexRunToolResult)
    assert result.verdict == "needs_review"
    assert result.output == "A"
    assert result.metadata["mode"] == "text"
    assert result.metadata["convergence"] == 0.5
    assert "run_id" in result.metadata
    assert isinstance(result.metadata["timings_ms"]["ensemble"], int)
    assert isinstance(result.metadata["timings_ms"]["adversarial"], int)
    assert captured["signals"].execution_required is False
    assert captured["signals"].execution_pass is None


def test_apex_run_code_mode_backend_error_downgrades_execution_pass_none(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(orchestrator, "load_llm_client_from_env", lambda: _FakeClient("fake-code"))
    monkeypatch.setattr(orchestrator, "code_convergence", lambda solutions: 0.7)
    monkeypatch.setattr(orchestrator, "select_best_code", lambda solutions: 0)

    async def fake_generate_code_solution_variants(*, client, prompt: str, config):
        assert client.model == "fake-code"
        assert "write" in prompt.lower()
        assert hasattr(config, "runs")
        return [_solution_bundle()]

    async def fake_generate_code_tests(*, client, prompt: str, config, suite_label: str, temperature: float):
        assert client.model == "fake-code"
        assert suite_label in ("tests_v1", "tests_v2")
        v = 1 if suite_label == "tests_v1" else 2
        return _tests_bundle(v)

    async def fake_review_code(
        *,
        client,
        task_prompt: str,
        candidate,
        tests_files_by_suite,
        execution_passes,
        max_tokens: int,
    ):
        assert task_prompt.lower().startswith("write")
        assert execution_passes == [None, None]
        assert max_tokens > 0
        # Keep all findings non-high so we don't rely on adversarial severity.
        return AdversarialReview(
            findings=[Finding(severity="low", type="t", confidence=0.1, evidence="e")]
        )

    def fake_decide_verdict(signals):
        # Core behavioral contract: code mode requests execution, but backend failure yields `execution_pass=None`.
        assert signals.execution_required is True
        assert signals.execution_pass is None
        return "needs_review"

    monkeypatch.setattr(orchestrator, "generate_code_solution_variants", fake_generate_code_solution_variants)
    monkeypatch.setattr(orchestrator, "generate_code_tests", fake_generate_code_tests)
    monkeypatch.setattr(orchestrator, "review_code", fake_review_code)
    monkeypatch.setattr(orchestrator, "decide_verdict", fake_decide_verdict)

    def fake_load_execution_backend_from_env():
        raise ExecutionBackendError("backend unavailable in test")

    monkeypatch.setattr(orchestrator, "load_execution_backend_from_env", fake_load_execution_backend_from_env)

    result = asyncio.run(
        orchestrator.apex_run(
            prompt="write code: implement f",
            mode="code",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=True,
        )
    )

    assert result.verdict == "needs_review"
    assert result.metadata["ground_truth_enabled"] is True
    assert result.metadata["verification_scale"] == "execution_ground_truth"
    assert result.metadata["execution_passes"] == [None, None]
    assert result.execution is None


def test_apex_run_code_mode_backend_success_propagates_execution_pass_true(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(orchestrator, "load_llm_client_from_env", lambda: _FakeClient("fake-code"))
    monkeypatch.setattr(orchestrator, "code_convergence", lambda solutions: 0.7)
    monkeypatch.setattr(orchestrator, "select_best_code", lambda solutions: 0)

    async def fake_generate_code_solution_variants(*, client, prompt: str, config):
        return [_solution_bundle()]

    async def fake_generate_code_tests(*, client, prompt: str, config, suite_label: str, temperature: float):
        v = 1 if suite_label == "tests_v1" else 2
        return _tests_bundle(v)

    async def fake_review_code(
        *,
        client,
        task_prompt: str,
        candidate,
        tests_files_by_suite,
        execution_passes,
        max_tokens: int,
    ):
        assert execution_passes == [True, True]
        return AdversarialReview(
            findings=[Finding(severity="low", type="t", confidence=0.1, evidence="e")]
        )

    class _FakeBackend:
        async def execute(self, *, run_id: str, solution: CodeSolution, tests: CodeTests, limits):
            # Always pass to ensure `execution_pass=True`.
            return ExecutionResult(
                **{"pass": True}, stdout="ok", stderr="", duration_ms=1
            )

    captured = {}

    def fake_decide_verdict(signals):
        captured["execution_pass"] = signals.execution_pass
        assert signals.execution_required is True
        assert signals.execution_pass is True
        return "high_verified"

    monkeypatch.setattr(orchestrator, "generate_code_solution_variants", fake_generate_code_solution_variants)
    monkeypatch.setattr(orchestrator, "generate_code_tests", fake_generate_code_tests)
    monkeypatch.setattr(orchestrator, "review_code", fake_review_code)
    monkeypatch.setattr(orchestrator, "decide_verdict", fake_decide_verdict)
    monkeypatch.setattr(orchestrator, "load_execution_backend_from_env", lambda: _FakeBackend())

    result = asyncio.run(
        orchestrator.apex_run(
            prompt="write code: implement f",
            mode="code",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=True,
        )
    )

    assert result.verdict == "high_verified"
    assert result.metadata["execution_passes"] == [True, True]
    assert captured["execution_pass"] is True
    assert result.execution is not None

