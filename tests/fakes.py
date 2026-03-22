"""
Shared test doubles for the verification pipeline.

Keep fakes minimal: most suites monkeypatch ``text_mode`` / ``code_mode`` so LLM methods
are not exercised unless a test removes those patches.
"""

from __future__ import annotations

from typing import Any

from apex.models import CodeFile, CodeSolution, CodeTests


class FakeLLMClient:
    """Structural ``LLMClient`` for pipeline tests (default model ``fake``)."""

    def __init__(self, model: str = "fake") -> None:
        self.model = model

    async def complete_text(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        raise RuntimeError("FakeLLMClient.complete_text: patch text_mode / code_mode")

    async def complete_json_object(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        raise RuntimeError("FakeLLMClient.complete_json_object: patch text_mode / code_mode")


def sample_code_solution() -> CodeSolution:
    """Minimal valid solution bundle for code-mode fakes."""
    return CodeSolution(files=[CodeFile(path="solution.py", content="def f():\n    return 1\n")])


def sample_code_tests(*, variant: int = 1) -> CodeTests:
    """Pytest suite using ``test_solution.py`` (required by ``validate_code_bundles``)."""
    return CodeTests(
        files=[
            CodeFile(
                path="test_solution.py",
                content=f"def test_v(v={variant}):\n    assert True\n",
            )
        ],
        test_framework="pytest",
    )
