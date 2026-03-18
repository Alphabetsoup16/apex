from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from apex.llm_client import AnthropicMessagesClient
from apex.models import CodeSolution, CodeTests, TextCompletion


_TEXT_SYSTEM_PROMPT = """\
You are APEX, a verification-oriented assistant.

Return ONLY valid JSON with the following keys:
- "answer": the final answer text
- "key_claims": an array of short, checkable claims that the answer depends on

Rules:
- Output JSON only (no markdown, no code fences).
- Do not include reasoning or chain-of-thought.
"""

_CODE_SOLUTION_SYSTEM_PROMPT = """\
You are APEX and you must generate Python 3 code.

Return ONLY valid JSON with:
- "files": an array of files
  - each file has "path" and "content"

Rules:
- Output JSON only (no markdown, no code fences).
- Provide the main implementation in "solution.py".
- Do not include tests in this response.
- Do not include explanations.
"""

_CODE_TESTS_SYSTEM_PROMPT = """\
You are APEX and you must generate pytest tests for a given Python solution.

Return ONLY valid JSON with:
- "files": an array of files
  - each file has "path" and "content"
  - put tests in "test_solution.py"
- "test_framework": set to "pytest"

Rules:
- Output JSON only (no markdown, no code fences).
- The tests must be derived from the task requirements, not from guessing internal bugs.
"""


@dataclass(frozen=True)
class EnsembleConfig:
    runs: int
    temperatures: Tuple[float, ...]
    max_tokens: int


async def generate_text_variants(
    *,
    client: AnthropicMessagesClient,
    prompt: str,
    config: EnsembleConfig,
) -> list[TextCompletion]:
    variants: list[TextCompletion] = []
    for i in range(config.runs):
        user = f"Task:\n{prompt}\n\nAnswer as the best possible response."
        payload = await client.complete_json_object(
            system=_TEXT_SYSTEM_PROMPT,
            user=user,
            max_tokens=config.max_tokens,
            temperature=config.temperatures[i],
        )
        variants.append(TextCompletion.model_validate(payload))
    return variants


async def generate_code_solution_variants(
    *,
    client: AnthropicMessagesClient,
    prompt: str,
    config: EnsembleConfig,
) -> list[CodeSolution]:
    variants: list[CodeSolution] = []
    for i in range(config.runs):
        user = f"Task:\n{prompt}\n\nWrite the Python solution. Output must be JSON."
        payload = await client.complete_json_object(
            system=_CODE_SOLUTION_SYSTEM_PROMPT,
            user=user,
            max_tokens=config.max_tokens,
            temperature=config.temperatures[i],
        )
        variants.append(CodeSolution.model_validate(payload))
    return variants


async def generate_code_tests(
    *,
    client: AnthropicMessagesClient,
    prompt: str,
    config: EnsembleConfig,
    suite_label: str = "tests_v1",
    temperature: float = 0.2,
) -> CodeTests:
    # Tests are spec-derived only; we avoid including any code in the prompt here.
    user = (
        f"Task requirements:\n{prompt}\n\n"
        f"Now write pytest tests for {suite_label}."
    )
    payload = await client.complete_json_object(
        system=_CODE_TESTS_SYSTEM_PROMPT,
        user=user,
        max_tokens=config.max_tokens,
        temperature=temperature,
    )
    # Convert payload dict -> validated model
    # (payload is already a dict from the JSON client)
    return CodeTests.model_validate(payload)

