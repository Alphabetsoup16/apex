"""Regression-style eval: verdict + pipeline step order under deterministic fakes."""

from __future__ import annotations

import asyncio

import pytest

import apex.pipeline.code_mode_bindings as code_mode_bindings
import apex.pipeline.run as pipeline_run
import apex.pipeline.run_context as run_context
import apex.pipeline.text_mode as text_mode
from apex.config.contracts import TELEMETRY_SCHEMA_V1, UNCERTAINTY_SCHEMA_V1
from apex.models import AdversarialReview, Finding, TextCompletion
from tests.eval.cases import ALL_CASES, RegressionCase
from tests.fakes import FakeLLMClient, sample_code_solution, sample_code_tests


def _patch_for_case(monkeypatch: pytest.MonkeyPatch, case: RegressionCase) -> None:
    if case.mode == "text":
        monkeypatch.setattr(
            run_context,
            "load_llm_client_from_env",
            lambda: FakeLLMClient("fake-text"),
        )

        if case.name == "text_standard":

            async def fake_generate_text_variants(*, client, prompt: str, config):
                return [
                    TextCompletion(answer="A", key_claims=["x"]),
                    TextCompletion(answer="B", key_claims=["y"]),
                ]

            async def fake_review_text(*, client, task_prompt: str, candidate, max_tokens: int):
                return AdversarialReview(
                    findings=[Finding(severity="low", type="t", confidence=0.1, evidence="e")]
                )

            monkeypatch.setattr(text_mode, "generate_text_variants", fake_generate_text_variants)
            monkeypatch.setattr(text_mode, "review_text", fake_review_text)
            monkeypatch.setattr(text_mode, "text_convergence", lambda variants: 0.5)
            monkeypatch.setattr(text_mode, "select_best_text", lambda variants: 0)
            monkeypatch.setattr(text_mode, "decide_verdict", lambda signals: "needs_review")

        elif case.name == "text_cot_blocked":

            async def fake_generate_text_variants(*, client, prompt: str, config):
                return [
                    TextCompletion(
                        answer="I think we should do this. chain-of-thought: ...", key_claims=["x"]
                    ),
                    TextCompletion(answer="safe answer", key_claims=["y"]),
                ]

            async def fake_review_text(**kwargs):
                raise AssertionError("review_text should not run when CoT leakage is detected")

            monkeypatch.setattr(text_mode, "generate_text_variants", fake_generate_text_variants)
            monkeypatch.setattr(text_mode, "review_text", fake_review_text)
            monkeypatch.setattr(text_mode, "text_convergence", lambda variants: 0.9)
            monkeypatch.setattr(text_mode, "select_best_text", lambda variants: 0)
            monkeypatch.setattr(text_mode, "decide_verdict", lambda signals: "high_verified")

        else:
            raise AssertionError(f"unknown text case {case.name!r}")

    elif case.mode == "code":
        monkeypatch.setattr(
            run_context,
            "load_llm_client_from_env",
            lambda: FakeLLMClient("fake-code"),
        )

        if case.name in ("code_spec_only", "code_spec_policy_extras"):

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
                return AdversarialReview(
                    findings=[Finding(severity="low", type="t", confidence=0.1, evidence="e")]
                )

            async def fake_inspect_code_doc_only(**kwargs):
                assert kwargs.get("execution_passes") is None
                return AdversarialReview(findings=[])

            monkeypatch.setattr(
                code_mode_bindings,
                "generate_code_solution_variants",
                fake_generate_code_solution_variants,
            )
            monkeypatch.setattr(code_mode_bindings, "generate_code_tests", fake_generate_code_tests)
            monkeypatch.setattr(code_mode_bindings, "review_code", fake_review_code)
            monkeypatch.setattr(
                code_mode_bindings,
                "inspect_code_doc_only",
                fake_inspect_code_doc_only,
            )
            monkeypatch.setattr(code_mode_bindings, "code_convergence", lambda solutions: 0.99)
            monkeypatch.setattr(code_mode_bindings, "select_best_code", lambda solutions: 0)

        else:
            raise AssertionError(f"unknown code case {case.name!r}")

    else:
        raise AssertionError(f"unknown mode {case.mode!r}")


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c.name)
def test_regression_pipeline_steps_and_verdict(
    monkeypatch: pytest.MonkeyPatch,
    case: RegressionCase,
) -> None:
    _patch_for_case(monkeypatch, case)

    run_kw: dict = {
        "prompt": case.prompt,
        "mode": case.mode,
        "ensemble_runs": 3,
        "max_tokens": 123,
        "code_ground_truth": case.code_ground_truth,
        "known_good_baseline": case.known_good_baseline,
    }
    if case.findings_ignore_types:
        run_kw["findings_ignore_types"] = list(case.findings_ignore_types)
    if case.findings_ignore_severities:
        run_kw["findings_ignore_severities"] = list(case.findings_ignore_severities)

    result = asyncio.run(pipeline_run.apex_run(**run_kw))

    assert result.verdict == case.expect_verdict
    steps = result.metadata.get("pipeline_steps") or []
    assert tuple(s["id"] for s in steps) == case.expect_step_ids
    tel = result.metadata.get("telemetry") or {}
    assert tel.get("schema") == TELEMETRY_SCHEMA_V1
    assert len(tel.get("spans") or []) == len(steps)
    assert (result.metadata.get("uncertainty") or {}).get("schema") == UNCERTAINTY_SCHEMA_V1
