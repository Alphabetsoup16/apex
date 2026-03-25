import asyncio

import pytest

import apex.pipeline.code_mode_bindings as code_mode_bindings
import apex.pipeline.run as pipeline_run
import apex.pipeline.run_context as run_context
import apex.pipeline.text_mode as text_mode
from apex.code_ground_truth.executor_client import ExecutionBackendError
from apex.config.policy import merge_findings_policy as merge_findings_policy_fn
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
from apex.pipeline import run_execute
from tests.fakes import FakeLLMClient, sample_code_solution, sample_code_tests


def test_apex_run_text_mode_uses_review_and_sets_signals(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-text"))

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

    monkeypatch.setattr(text_mode, "generate_text_variants", fake_generate_text_variants)
    monkeypatch.setattr(text_mode, "review_text", fake_review_text)
    monkeypatch.setattr(text_mode, "text_convergence", lambda variants: 0.5)
    monkeypatch.setattr(text_mode, "select_best_text", lambda variants: 0)

    captured = {}

    def fake_decide_verdict(signals):
        captured["signals"] = signals
        return "needs_review"

    monkeypatch.setattr(text_mode, "decide_verdict", fake_decide_verdict)

    result = asyncio.run(
        pipeline_run.apex_run(
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
    steps = result.metadata.get("pipeline_steps")
    assert steps
    assert [s["id"] for s in steps] == [
        "ensemble",
        "cot_audit",
        "adversarial_review",
        "baseline_alignment",
    ]
    assert all(s["ok"] for s in steps)


def test_apex_run_code_mode_backend_error_downgrades_execution_pass_none(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-code"))
    monkeypatch.setattr(code_mode_bindings, "code_convergence", lambda solutions: 0.7)
    monkeypatch.setattr(code_mode_bindings, "select_best_code", lambda solutions: 0)

    async def fake_generate_code_solution_variants(*, client, prompt: str, config):
        assert client.model == "fake-code"
        assert "write" in prompt.lower()
        assert hasattr(config, "runs")
        return [sample_code_solution()]

    async def fake_generate_code_tests(
        *, client, prompt: str, config, suite_label: str, temperature: float
    ):
        assert client.model == "fake-code"
        assert suite_label in ("tests_v1", "tests_v2")
        v = 1 if suite_label == "tests_v1" else 2
        return sample_code_tests(variant=v)

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

    async def fake_inspect_code_doc_only(**kwargs):
        return AdversarialReview(findings=[])

    def fake_decide_verdict(signals):
        # Core behavioral contract: code mode requests execution,
        # but backend failure yields `execution_pass=None`.
        assert signals.execution_required is True
        assert signals.execution_pass is None
        return "needs_review"

    monkeypatch.setattr(
        code_mode_bindings, "generate_code_solution_variants", fake_generate_code_solution_variants
    )
    monkeypatch.setattr(code_mode_bindings, "generate_code_tests", fake_generate_code_tests)
    monkeypatch.setattr(code_mode_bindings, "review_code", fake_review_code)
    monkeypatch.setattr(code_mode_bindings, "inspect_code_doc_only", fake_inspect_code_doc_only)
    monkeypatch.setattr(code_mode_bindings, "decide_verdict", fake_decide_verdict)

    def fake_load_execution_backend_from_env():
        raise ExecutionBackendError("backend unavailable in test")

    monkeypatch.setattr(
        code_mode_bindings, "load_execution_backend_from_env", fake_load_execution_backend_from_env
    )

    result = asyncio.run(
        pipeline_run.apex_run(
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


def test_apex_run_code_mode_wires_findings_overrides_into_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guards silent drift: per-run lists must reach ``merge_findings_policy`` on the code path."""
    merge_snapshots: list[tuple[tuple[str, ...], tuple[str, ...]]] = []

    def capturing_merge(base, *, extra_ignored_types=(), extra_ignored_severities=()):
        merge_snapshots.append((tuple(extra_ignored_types), tuple(extra_ignored_severities)))
        return merge_findings_policy_fn(
            base,
            extra_ignored_types=extra_ignored_types,
            extra_ignored_severities=extra_ignored_severities,
        )

    monkeypatch.setattr(run_execute, "merge_findings_policy", capturing_merge)

    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-code"))
    monkeypatch.setattr(code_mode_bindings, "code_convergence", lambda solutions: 0.7)
    monkeypatch.setattr(code_mode_bindings, "select_best_code", lambda solutions: 0)

    async def fake_generate_code_solution_variants(*, client, prompt: str, config):
        return [sample_code_solution()]

    async def fake_generate_code_tests(
        *, client, prompt: str, config, suite_label: str, temperature: float
    ):
        v = 1 if suite_label == "tests_v1" else 2
        return sample_code_tests(variant=v)

    async def fake_review_code(**kwargs):
        return AdversarialReview(
            findings=[Finding(severity="low", type="t", confidence=0.1, evidence="e")]
        )

    async def fake_inspect_code_doc_only(**kwargs):
        return AdversarialReview(findings=[])

    monkeypatch.setattr(
        code_mode_bindings, "generate_code_solution_variants", fake_generate_code_solution_variants
    )
    monkeypatch.setattr(code_mode_bindings, "generate_code_tests", fake_generate_code_tests)
    monkeypatch.setattr(code_mode_bindings, "review_code", fake_review_code)
    monkeypatch.setattr(code_mode_bindings, "inspect_code_doc_only", fake_inspect_code_doc_only)
    monkeypatch.setattr(code_mode_bindings, "decide_verdict", lambda signals: "needs_review")

    def fake_load_execution_backend_from_env():
        raise ExecutionBackendError("backend unavailable in test")

    monkeypatch.setattr(
        code_mode_bindings, "load_execution_backend_from_env", fake_load_execution_backend_from_env
    )

    asyncio.run(
        pipeline_run.apex_run(
            prompt="write code: implement f",
            mode="code",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=True,
            findings_ignore_types=["slot_noise"],
            findings_ignore_severities=["info"],
        )
    )

    assert merge_snapshots == [(("slot_noise",), ("info",))]


def test_apex_run_code_mode_backend_success_propagates_execution_pass_true(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-code"))
    monkeypatch.setattr(code_mode_bindings, "code_convergence", lambda solutions: 0.7)
    monkeypatch.setattr(code_mode_bindings, "select_best_code", lambda solutions: 0)

    async def fake_generate_code_solution_variants(*, client, prompt: str, config):
        return [sample_code_solution()]

    async def fake_generate_code_tests(
        *, client, prompt: str, config, suite_label: str, temperature: float
    ):
        v = 1 if suite_label == "tests_v1" else 2
        return sample_code_tests(variant=v)

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

    async def fake_inspect_code_doc_only(**kwargs):
        assert kwargs.get("execution_passes") == [True, True]
        return AdversarialReview(findings=[])

    class _FakeBackend:
        async def execute(self, *, run_id: str, solution: CodeSolution, tests: CodeTests, limits):
            # Always pass to ensure `execution_pass=True`.
            return ExecutionResult(**{"pass": True}, stdout="ok", stderr="", duration_ms=1)

    captured = {}

    def fake_decide_verdict(signals):
        captured["execution_pass"] = signals.execution_pass
        assert signals.execution_required is True
        assert signals.execution_pass is True
        assert signals.adversarial_high is False
        return "high_verified"

    monkeypatch.setattr(
        code_mode_bindings, "generate_code_solution_variants", fake_generate_code_solution_variants
    )
    monkeypatch.setattr(code_mode_bindings, "generate_code_tests", fake_generate_code_tests)
    monkeypatch.setattr(code_mode_bindings, "review_code", fake_review_code)
    monkeypatch.setattr(code_mode_bindings, "inspect_code_doc_only", fake_inspect_code_doc_only)
    monkeypatch.setattr(code_mode_bindings, "decide_verdict", fake_decide_verdict)
    monkeypatch.setattr(
        code_mode_bindings,
        "load_execution_backend_from_env",
        lambda: _FakeBackend(),
    )

    result = asyncio.run(
        pipeline_run.apex_run(
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


def test_apex_run_code_mode_execution_http_records_suite_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-code"))
    monkeypatch.setattr(code_mode_bindings, "code_convergence", lambda solutions: 0.7)
    monkeypatch.setattr(code_mode_bindings, "select_best_code", lambda solutions: 0)

    async def fake_generate_code_solution_variants(*, client, prompt: str, config):
        return [sample_code_solution()]

    async def fake_generate_code_tests(
        *, client, prompt: str, config, suite_label: str, temperature: float
    ):
        v = 1 if suite_label == "tests_v1" else 2
        return sample_code_tests(variant=v)

    async def fake_review_code(
        *,
        client,
        task_prompt: str,
        candidate,
        tests_files_by_suite,
        execution_passes,
        max_tokens: int,
    ):
        assert execution_passes == [None, None]
        return AdversarialReview(
            findings=[Finding(severity="low", type="t", confidence=0.1, evidence="e")]
        )

    async def fake_inspect_code_doc_only(**kwargs):
        return AdversarialReview(findings=[])

    class _ErrBackend:
        async def execute(self, *, run_id: str, solution: CodeSolution, tests: CodeTests, limits):
            raise ExecutionBackendError("temporary", reason="http_error", http_status=502)

    monkeypatch.setattr(
        code_mode_bindings, "generate_code_solution_variants", fake_generate_code_solution_variants
    )
    monkeypatch.setattr(code_mode_bindings, "generate_code_tests", fake_generate_code_tests)
    monkeypatch.setattr(code_mode_bindings, "review_code", fake_review_code)
    monkeypatch.setattr(code_mode_bindings, "inspect_code_doc_only", fake_inspect_code_doc_only)
    monkeypatch.setattr(code_mode_bindings, "decide_verdict", lambda signals: "needs_review")
    monkeypatch.setattr(
        code_mode_bindings,
        "load_execution_backend_from_env",
        lambda: _ErrBackend(),
    )

    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="write code: implement f",
            mode="code",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=True,
        )
    )

    assert result.verdict == "needs_review"
    errs = result.metadata.get("execution_suite_errors") or []
    assert len(errs) == 2
    assert {e["suite"] for e in errs} == {0, 1}
    assert all(e["reason"] == "http_error" and e["http_status"] == 502 for e in errs)
    assert all(isinstance(e.get("message"), str) and "temporary" in e["message"] for e in errs)


def test_apex_run_code_mode_review_pack_output(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-code"))
    monkeypatch.setattr(code_mode_bindings, "code_convergence", lambda solutions: 0.99)
    monkeypatch.setattr(code_mode_bindings, "select_best_code", lambda solutions: 0)

    async def fake_generate_code_solution_variants(*, client, prompt: str, config):
        return [sample_code_solution()]

    async def fake_generate_code_tests(
        *, client, prompt: str, config, suite_label: str, temperature: float
    ):
        return sample_code_tests(variant=1 if suite_label == "tests_v1" else 2)

    async def fake_review_code(**kwargs):
        return AdversarialReview(findings=[])

    async def fake_inspect_code_doc_only(**kwargs):
        return AdversarialReview(
            findings=[
                Finding(severity="medium", type="structure", confidence=0.7, evidence="duplication")
            ]
        )

    class _FakeBackend:
        async def execute(self, *, run_id: str, solution: CodeSolution, tests: CodeTests, limits):
            return ExecutionResult(**{"pass": True}, stdout="ok", stderr="", duration_ms=1)

    monkeypatch.setattr(
        code_mode_bindings, "generate_code_solution_variants", fake_generate_code_solution_variants
    )
    monkeypatch.setattr(code_mode_bindings, "generate_code_tests", fake_generate_code_tests)
    monkeypatch.setattr(code_mode_bindings, "review_code", fake_review_code)
    monkeypatch.setattr(code_mode_bindings, "inspect_code_doc_only", fake_inspect_code_doc_only)
    monkeypatch.setattr(
        code_mode_bindings,
        "load_execution_backend_from_env",
        lambda: _FakeBackend(),
    )

    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="write code: implement f",
            mode="code",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=True,
            output_mode="review_pack",
            language="csharp",
            diff="diff --git a/a.cs b/b.cs",
            repo_conventions="- Prefer async/await\n- No duplicated helpers",
        )
    )

    assert result.output.startswith("## APEX PR Review Pack")
    assert "Should fix (medium)" in result.output
    assert result.metadata["output_mode"] == "review_pack"


def test_apex_run_code_mode_blocks_on_cot_leakage(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-code"))
    monkeypatch.setattr(code_mode_bindings, "code_convergence", lambda solutions: 0.5)
    monkeypatch.setattr(code_mode_bindings, "select_best_code", lambda solutions: 0)

    async def fake_generate_code_solution_variants(*, client, prompt: str, config):
        # Put a CoT marker inside the generated code comment.
        return [
            CodeSolution(
                files=[
                    CodeFile(
                        path="solution.py",
                        content="# chain-of-thought: this is forbidden\n\ndef f():\n    return 1\n",
                    )
                ]
            )
        ]

    async def fake_generate_code_tests(
        *, client, prompt: str, config, suite_label: str, temperature: float
    ):
        raise AssertionError("generate_code_tests should not run when CoT leakage is detected")

    async def fake_review_code(**kwargs):
        raise AssertionError("review_code should not run when CoT leakage is detected")

    monkeypatch.setattr(
        code_mode_bindings, "generate_code_solution_variants", fake_generate_code_solution_variants
    )
    monkeypatch.setattr(code_mode_bindings, "generate_code_tests", fake_generate_code_tests)
    monkeypatch.setattr(code_mode_bindings, "review_code", fake_review_code)

    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="write code: implement f",
            mode="code",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=False,
        )
    )

    assert result.verdict == "blocked"
    assert result.adversarial_review is None
    assert result.execution is None
    assert result.metadata.get("cot_audit", {}).get("detected") is True


def test_apex_run_code_mode_inspection_high_blocks_verdict(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-code"))
    monkeypatch.setattr(code_mode_bindings, "code_convergence", lambda solutions: 0.99)
    monkeypatch.setattr(code_mode_bindings, "select_best_code", lambda solutions: 0)

    async def fake_generate_code_solution_variants(*, client, prompt: str, config):
        return [sample_code_solution()]

    async def fake_generate_code_tests(
        *, client, prompt: str, config, suite_label: str, temperature: float
    ):
        v = 1 if suite_label == "tests_v1" else 2
        return sample_code_tests(variant=v)

    async def fake_review_code(
        *,
        client,
        task_prompt: str,
        candidate,
        tests_files_by_suite,
        execution_passes,
        max_tokens: int,
    ):
        # No adversarial findings from the adversarial reviewer.
        assert execution_passes == [True, True]
        return AdversarialReview(findings=[])

    async def fake_inspect_code_doc_only(**kwargs):
        assert kwargs.get("execution_passes") == [True, True]
        return AdversarialReview(
            findings=[
                Finding(
                    severity="high",
                    type="t",
                    confidence=0.9,
                    evidence="doc-based high issue",
                )
            ]
        )

    class _FakeBackend:
        async def execute(self, *, run_id: str, solution: CodeSolution, tests: CodeTests, limits):
            return ExecutionResult(
                **{"pass": True},
                stdout="ok",
                stderr="",
                duration_ms=1,
            )

    monkeypatch.setattr(
        code_mode_bindings, "generate_code_solution_variants", fake_generate_code_solution_variants
    )
    monkeypatch.setattr(code_mode_bindings, "generate_code_tests", fake_generate_code_tests)
    monkeypatch.setattr(code_mode_bindings, "review_code", fake_review_code)
    monkeypatch.setattr(code_mode_bindings, "inspect_code_doc_only", fake_inspect_code_doc_only)
    monkeypatch.setattr(
        code_mode_bindings,
        "load_execution_backend_from_env",
        lambda: _FakeBackend(),
    )

    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="write code: implement f",
            mode="code",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=True,
        )
    )

    assert result.verdict == "blocked"
    assert result.metadata["execution_passes"] == [True, True]
    assert "inspection_review" in result.metadata


def test_apex_run_code_mode_inspection_medium_does_not_block(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-code"))
    monkeypatch.setattr(code_mode_bindings, "code_convergence", lambda solutions: 0.99)
    monkeypatch.setattr(code_mode_bindings, "select_best_code", lambda solutions: 0)

    async def fake_generate_code_solution_variants(*, client, prompt: str, config):
        return [sample_code_solution()]

    async def fake_generate_code_tests(
        *, client, prompt: str, config, suite_label: str, temperature: float
    ):
        v = 1 if suite_label == "tests_v1" else 2
        return sample_code_tests(variant=v)

    async def fake_review_code(
        *,
        client,
        task_prompt: str,
        candidate,
        tests_files_by_suite,
        execution_passes,
        max_tokens: int,
    ):
        # No adversarial findings.
        assert execution_passes == [True, True]
        return AdversarialReview(findings=[])

    async def fake_inspect_code_doc_only(**kwargs):
        # Medium inspection findings should be reported, but not block/downgrade.
        assert kwargs.get("execution_passes") == [True, True]
        return AdversarialReview(
            findings=[
                Finding(
                    severity="medium",
                    type="t",
                    confidence=0.7,
                    evidence="doc-based medium issue",
                )
            ]
        )

    class _FakeBackend:
        async def execute(self, *, run_id: str, solution: CodeSolution, tests: CodeTests, limits):
            return ExecutionResult(
                **{"pass": True},
                stdout="ok",
                stderr="",
                duration_ms=1,
            )

    monkeypatch.setattr(
        code_mode_bindings, "generate_code_solution_variants", fake_generate_code_solution_variants
    )
    monkeypatch.setattr(code_mode_bindings, "generate_code_tests", fake_generate_code_tests)
    monkeypatch.setattr(code_mode_bindings, "review_code", fake_review_code)
    monkeypatch.setattr(code_mode_bindings, "inspect_code_doc_only", fake_inspect_code_doc_only)
    monkeypatch.setattr(
        code_mode_bindings,
        "load_execution_backend_from_env",
        lambda: _FakeBackend(),
    )

    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="write code: implement f",
            mode="code",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=True,
        )
    )

    assert result.verdict == "high_verified"
    assert result.metadata["execution_passes"] == [True, True]
    assert result.metadata["inspection_review"]["findings"][0]["severity"] == "medium"


def test_apex_run_mode_auto_blocks_on_missing_test_solution_py(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-code"))
    monkeypatch.setattr(code_mode_bindings, "code_convergence", lambda solutions: 0.5)
    monkeypatch.setattr(code_mode_bindings, "select_best_code", lambda solutions: 0)

    async def fake_generate_code_solution_variants(*, client, prompt: str, config):
        assert client.model == "fake-code"
        return [sample_code_solution()]

    async def fake_generate_code_tests(
        *, client, prompt: str, config, suite_label: str, temperature: float
    ):
        assert suite_label in ("tests_v1", "tests_v2")
        if suite_label == "tests_v1":
            # Missing `test_solution.py` should trigger `validate_code_bundles` failure.
            return CodeTests(
                files=[CodeFile(path="not_test_solution.py", content="x = 1\n")],
                test_framework="pytest",
            )
        # This will be scheduled (because code_ground_truth=True) but should be cancelled.
        await asyncio.sleep(0.05)
        return sample_code_tests(variant=2)

    async def fake_review_code(**kwargs):
        raise AssertionError("review_code should not be called when tests bundle validation fails")

    async def fake_inspect_code_doc_only(**kwargs):
        raise AssertionError(
            "inspect_code_doc_only should not be called when tests bundle validation fails"
        )

    monkeypatch.setattr(
        code_mode_bindings, "generate_code_solution_variants", fake_generate_code_solution_variants
    )
    monkeypatch.setattr(code_mode_bindings, "generate_code_tests", fake_generate_code_tests)
    monkeypatch.setattr(code_mode_bindings, "review_code", fake_review_code)
    monkeypatch.setattr(code_mode_bindings, "inspect_code_doc_only", fake_inspect_code_doc_only)

    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="write code: implement f",
            mode="auto",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=True,
        )
    )

    assert result.verdict == "blocked"
    assert result.adversarial_review is None
    assert result.execution is None
    assert result.metadata["mode"] == "code"
    # In-pipeline block (``blocked_run_result``) still carries the concrete validation token.
    assert "missing_test_solution_py" in result.metadata.get("error", "")


def test_apex_run_top_level_value_error_uses_sanitized_metadata(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-text"))

    def boom(**kwargs):
        raise ValueError("missing_test_solution_py")

    monkeypatch.setattr(run_execute, "load_effective_conventions", boom)
    monkeypatch.delenv("APEX_EXPOSE_ERROR_DETAILS", raising=False)

    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="hello",
            mode="text",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=False,
        )
    )
    assert result.verdict == "blocked"
    md = result.metadata
    assert md.get("error_code") == "apex.validation"
    assert "Validation failed" in md.get("error", "")
    assert "missing_test_solution_py" not in md.get("error", "")
    assert "error_detail" not in md

    monkeypatch.setenv("APEX_EXPOSE_ERROR_DETAILS", "1")
    result2 = asyncio.run(
        pipeline_run.apex_run(
            prompt="hello",
            mode="text",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=False,
        )
    )
    assert "missing_test_solution_py" in result2.metadata.get("error_detail", "")


def test_apex_run_code_ground_truth_false_never_high_verified(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-code"))

    async def fake_generate_code_solution_variants(*, client, prompt: str, config):
        return [sample_code_solution()]

    async def fake_generate_code_tests(
        *, client, prompt: str, config, suite_label: str, temperature: float
    ):
        assert suite_label == "tests_v1"
        return sample_code_tests(variant=1)

    async def fake_review_code(
        *,
        client,
        task_prompt: str,
        candidate,
        tests_files_by_suite,
        execution_passes,
        max_tokens: int,
    ):
        assert execution_passes is None
        assert task_prompt.lower().startswith("write code")
        return AdversarialReview(
            findings=[Finding(severity="low", type="t", confidence=0.1, evidence="e")]
        )

    async def fake_inspect_code_doc_only(**kwargs):
        assert kwargs.get("execution_passes") is None
        assert str(kwargs.get("task_prompt", "")).lower().startswith("write code")
        return AdversarialReview(findings=[])

    monkeypatch.setattr(
        code_mode_bindings, "generate_code_solution_variants", fake_generate_code_solution_variants
    )
    monkeypatch.setattr(code_mode_bindings, "generate_code_tests", fake_generate_code_tests)
    monkeypatch.setattr(code_mode_bindings, "review_code", fake_review_code)
    monkeypatch.setattr(code_mode_bindings, "inspect_code_doc_only", fake_inspect_code_doc_only)

    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="write code: implement f",
            mode="code",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=False,
        )
    )

    assert result.verdict == "needs_review"
    assert result.metadata["ground_truth_enabled"] is False
    assert result.metadata["verification_scale"] == "spec_only"
    assert result.metadata["execution_passes"] is None
    assert result.execution is None


def test_apex_run_code_ground_truth_one_suite_fails_blocks(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-code"))

    async def fake_generate_code_solution_variants(*, client, prompt: str, config):
        return [sample_code_solution()]

    async def fake_generate_code_tests(
        *, client, prompt: str, config, suite_label: str, temperature: float
    ):
        if suite_label == "tests_v1":
            return sample_code_tests(variant=1)
        return sample_code_tests(variant=2)

    async def fake_review_code(
        *,
        client,
        task_prompt: str,
        candidate,
        tests_files_by_suite,
        execution_passes,
        max_tokens: int,
    ):
        assert execution_passes == [True, False]
        return AdversarialReview(
            findings=[Finding(severity="low", type="t", confidence=0.1, evidence="e")]
        )

    async def fake_inspect_code_doc_only(**kwargs):
        assert kwargs.get("execution_passes") == [True, False]
        assert str(kwargs.get("task_prompt", "")).lower().startswith("write")
        return AdversarialReview(findings=[])

    class _FakeBackend:
        async def execute(self, *, run_id: str, solution: CodeSolution, tests: CodeTests, limits):
            # code_mode uses: f"{run_id}-suite{suite_idx}"
            suite_idx = 0 if run_id.endswith("-suite0") else 1
            pass_val = suite_idx == 0
            return ExecutionResult(
                **{"pass": pass_val},
                stdout=f"suite{suite_idx} stdout",
                stderr="",
                duration_ms=1,
            )

    monkeypatch.setattr(
        code_mode_bindings, "generate_code_solution_variants", fake_generate_code_solution_variants
    )
    monkeypatch.setattr(code_mode_bindings, "generate_code_tests", fake_generate_code_tests)
    monkeypatch.setattr(code_mode_bindings, "review_code", fake_review_code)
    monkeypatch.setattr(code_mode_bindings, "inspect_code_doc_only", fake_inspect_code_doc_only)
    monkeypatch.setattr(
        code_mode_bindings,
        "load_execution_backend_from_env",
        lambda: _FakeBackend(),
    )

    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="write code: implement f",
            mode="code",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=True,
        )
    )

    assert result.verdict == "blocked"
    assert result.metadata["execution_passes"] == [True, False]
    assert result.execution is not None
    assert result.execution.pass_ is True


def test_apex_run_text_mode_blocks_on_cot_leakage(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-text"))

    async def fake_generate_text_variants(*, client, prompt: str, config):
        return [
            TextCompletion(
                answer="I think we should do this. chain-of-thought: ...", key_claims=["x"]
            ),
            TextCompletion(answer="safe answer", key_claims=["y"]),
        ]

    async def fake_review_text(**kwargs):
        raise AssertionError("review_text should not be called when CoT leakage is detected")

    monkeypatch.setattr(text_mode, "generate_text_variants", fake_generate_text_variants)
    monkeypatch.setattr(text_mode, "review_text", fake_review_text)
    monkeypatch.setattr(text_mode, "text_convergence", lambda variants: 0.9)
    monkeypatch.setattr(text_mode, "select_best_text", lambda variants: 0)
    monkeypatch.setattr(text_mode, "decide_verdict", lambda signals: "high_verified")

    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="hello",
            mode="text",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=False,
            known_good_baseline="irrelevant",
        )
    )

    assert result.verdict == "blocked"
    assert result.adversarial_review is None
    assert result.execution is None
    steps = result.metadata.get("pipeline_steps")
    assert steps
    assert [s["id"] for s in steps] == ["ensemble", "cot_audit"]
    assert steps[-1]["ok"] is False


def test_apex_run_text_mode_baseline_downgrades_high_verified(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-text"))

    async def fake_generate_text_variants(*, client, prompt: str, config):
        return [
            TextCompletion(answer="EXPECTED OUTPUT", key_claims=["x"]),
            TextCompletion(answer="OTHER OUTPUT", key_claims=["y"]),
        ]

    async def fake_review_text(*, client, task_prompt: str, candidate, max_tokens: int):
        return AdversarialReview(findings=[])

    monkeypatch.setattr(text_mode, "generate_text_variants", fake_generate_text_variants)
    monkeypatch.setattr(text_mode, "review_text", fake_review_text)
    monkeypatch.setattr(text_mode, "text_convergence", lambda variants: 0.99)
    monkeypatch.setattr(text_mode, "select_best_text", lambda variants: 0)

    # Baseline is intentionally far from "EXPECTED OUTPUT".
    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="hello",
            mode="text",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=False,
            known_good_baseline="COMPLETELY DIFFERENT BASELINE TEXT",
        )
    )

    assert result.verdict == "needs_review"
    assert result.metadata["baseline_similarity"] is not None
    assert result.output == "EXPECTED OUTPUT"


def test_apex_run_code_mode_baseline_downgrades_high_verified(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-code"))
    monkeypatch.setattr(code_mode_bindings, "code_convergence", lambda solutions: 0.99)
    monkeypatch.setattr(code_mode_bindings, "select_best_code", lambda solutions: 0)

    async def fake_generate_code_solution_variants(*, client, prompt: str, config):
        return [sample_code_solution()]

    async def fake_generate_code_tests(
        *, client, prompt: str, config, suite_label: str, temperature: float
    ):
        return sample_code_tests(variant=1 if suite_label == "tests_v1" else 2)

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

    async def fake_inspect_code_doc_only(**kwargs):
        assert kwargs.get("execution_passes") == [True, True]
        return AdversarialReview(findings=[])

    class _FakeBackend:
        async def execute(self, *, run_id: str, solution: CodeSolution, tests: CodeTests, limits):
            return ExecutionResult(
                **{"pass": True},
                stdout="ok",
                stderr="",
                duration_ms=1,
            )

    monkeypatch.setattr(
        code_mode_bindings, "generate_code_solution_variants", fake_generate_code_solution_variants
    )
    monkeypatch.setattr(code_mode_bindings, "generate_code_tests", fake_generate_code_tests)
    monkeypatch.setattr(code_mode_bindings, "review_code", fake_review_code)
    monkeypatch.setattr(code_mode_bindings, "inspect_code_doc_only", fake_inspect_code_doc_only)
    monkeypatch.setattr(
        code_mode_bindings,
        "load_execution_backend_from_env",
        lambda: _FakeBackend(),
    )

    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="write code: implement f",
            mode="code",
            ensemble_runs=3,
            max_tokens=123,
            code_ground_truth=True,
            known_good_baseline="COMPLETELY DIFFERENT BASELINE TEXT",
        )
    )

    assert result.verdict == "needs_review"
    assert result.metadata["baseline_similarity"] is not None
    assert result.execution is not None


def test_apex_run_top_level_exception_has_rich_metadata(monkeypatch: pytest.MonkeyPatch):
    long_msg = "e" * 2500

    def boom() -> None:
        raise RuntimeError(long_msg)

    monkeypatch.setattr(run_context, "load_llm_client_from_env", boom)
    monkeypatch.delenv("APEX_EXPOSE_ERROR_DETAILS", raising=False)

    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="hello",
            mode="text",
            ensemble_runs=5,
            max_tokens=512,
            code_ground_truth=False,
        )
    )
    assert isinstance(result, ApexRunToolResult)
    assert result.verdict == "blocked"
    md = result.metadata
    assert md["ensemble_runs_requested"] == 5
    assert md["ensemble_runs_effective"] == 3
    assert md["mode_request"] == "text"
    assert md["mode_inferred"] is None
    assert md["mode"] == "text"
    assert md["error_code"] == "apex.internal"
    assert md["error_type"] == "RuntimeError"
    assert md["error"] != long_msg
    assert long_msg not in md["error"]
    assert "error_detail" not in md
    assert md["pipeline_steps"] == []
    assert "total" in md["timings_ms"]


def test_apex_run_top_level_exception_includes_error_detail_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
):
    long_msg = "e" * 2500

    def boom() -> None:
        raise RuntimeError(long_msg)

    monkeypatch.setattr(run_context, "load_llm_client_from_env", boom)
    monkeypatch.setenv("APEX_EXPOSE_ERROR_DETAILS", "1")

    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="hello",
            mode="text",
            ensemble_runs=3,
            max_tokens=512,
            code_ground_truth=False,
        )
    )
    md = result.metadata
    assert md["error_detail"] == long_msg


def test_apex_run_success_includes_ensemble_request_metadata(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(run_context, "load_llm_client_from_env", lambda: FakeLLMClient("fake-text"))

    async def fake_generate_text_variants(*, client, prompt: str, config):
        return [TextCompletion(answer="ok", key_claims=["x"])]

    async def fake_review_text(**kwargs):
        return AdversarialReview(findings=[])

    monkeypatch.setattr(text_mode, "generate_text_variants", fake_generate_text_variants)
    monkeypatch.setattr(text_mode, "review_text", fake_review_text)
    monkeypatch.setattr(text_mode, "text_convergence", lambda variants: 0.99)
    monkeypatch.setattr(text_mode, "select_best_text", lambda variants: 0)
    monkeypatch.setattr(text_mode, "decide_verdict", lambda signals: "high_verified")

    result = asyncio.run(
        pipeline_run.apex_run(
            prompt="hello",
            mode="text",
            ensemble_runs=1,
            max_tokens=100,
            code_ground_truth=False,
        )
    )
    assert result.metadata["ensemble_runs_requested"] == 1
    assert result.metadata["ensemble_runs_effective"] == 2
