import asyncio
from typing import Any

from apex.generation.ensemble import EnsembleConfig, generate_code_tests, generate_text_variants
from apex.llm.interface import LLMClient
from apex.models import CodeTests, TextCompletion


class FakeLLMClient:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    @property
    def model(self) -> str:
        return "fake-model"

    async def complete_text(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        # Not used by these tests.
        raise NotImplementedError

    async def complete_json_object(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )

        # Decide which schema we are asked for based on system prompt.
        if "key_claims" in system:
            # TextCompletion
            if temperature < 0.5:
                return {"answer": "A", "key_claims": ["claim_a"]}
            return {"answer": "B", "key_claims": ["claim_b"]}

        # CodeTests
        return {
            "files": [
                {
                    "path": "test_solution.py",
                    "content": "def test_x():\n    assert True\n",
                }
            ],
            "test_framework": "pytest",
        }


async def _run_generate_code_tests(fake: FakeLLMClient) -> CodeTests:
    cfg = EnsembleConfig(runs=2, temperatures=(0.2, 0.8), max_tokens=123)
    return await generate_code_tests(
        client=fake,
        prompt="spec: do something",
        config=cfg,
        suite_label="tests_v2",
        temperature=0.5,
    )


def test_generate_code_tests_suite_label_is_used():
    fake: LLMClient = FakeLLMClient()
    out = asyncio.run(_run_generate_code_tests(fake))
    assert isinstance(out, CodeTests)
    assert any("tests_v2" in c["user"] for c in fake.calls)


def test_generate_text_variants_calls_two_runs_with_temperatures():
    fake: LLMClient = FakeLLMClient()
    cfg = EnsembleConfig(runs=2, temperatures=(0.2, 0.8), max_tokens=50)

    async def _run():
        variants: list[TextCompletion] = await generate_text_variants(
            client=fake,
            prompt="spec: answer",
            config=cfg,
        )
        return variants

    variants = asyncio.run(_run())
    assert [v.answer for v in variants] == ["A", "B"]
    assert [c["temperature"] for c in fake.calls] == [0.2, 0.8]
