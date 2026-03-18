from __future__ import annotations

from apex.llm_client import AnthropicMessagesClient
from apex.models import AdversarialReview, CodeSolution, TextCompletion


_ADVERSARIAL_SYSTEM_PROMPT = """\
You are a senior adversarial reviewer.

Your ONLY task is to find problems in the candidate output:
- incorrect assumptions
- missing edge cases
- internal inconsistencies
- contradictions with the task requirements
- security issues

Return ONLY valid JSON with this schema:
{
  "findings": [
    {
      "severity": "high" | "medium" | "low",
      "type": "string category",
      "confidence": 0.0,
      "evidence": "verbatim mismatch evidence",
      "location": "optional",
      "recommendation": "optional"
    }
  ]
}

Rules:
- Output JSON only (no markdown).
- Do not restate the entire candidate output.
- If there are no meaningful issues, return {"findings": []}.
"""


def _truncate(s: str, *, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "\n\n[TRUNCATED]"


async def review_text(
    *,
    client: AnthropicMessagesClient,
    task_prompt: str,
    candidate: TextCompletion,
    max_tokens: int,
) -> AdversarialReview:
    candidate_answer = _truncate(candidate.answer, max_chars=12000)
    key_claims = candidate.key_claims[:50]
    user = (
        f"Task requirements:\n{task_prompt}\n\n"
        f"Candidate answer:\n{candidate_answer}\n\n"
        f"Candidate key claims:\n{key_claims}\n\n"
        "Find problems."
    )
    payload = await client.complete_json_object(
        system=_ADVERSARIAL_SYSTEM_PROMPT,
        user=user,
        max_tokens=max_tokens,
        temperature=0.0,
    )
    return AdversarialReview.model_validate(payload)


async def review_code(
    *,
    client: AnthropicMessagesClient,
    task_prompt: str,
    candidate: CodeSolution,
    tests_files: list[dict] | None,
    execution_pass: bool | None,
    max_tokens: int,
) -> AdversarialReview:
    solution_files = "\n".join(
        [f"--- {f.path} ---\n{f.content}" for f in candidate.files]
    )
    tests_info = ""
    if tests_files is not None:
        tests_info = "\n\nCandidate tests:\n" + "\n".join(
            [f"--- {f['path']} ---\n{f['content']}" for f in tests_files]
        )
    exec_info = ""
    if execution_pass is not None:
        exec_info = f"\n\nExecution result:\n- pass: {execution_pass}\n"

    solution_files = _truncate(solution_files, max_chars=20000)
    tests_info = _truncate(tests_info, max_chars=20000)
    user = (
        f"Task requirements:\n{task_prompt}\n\n"
        f"Candidate code:\n{solution_files}"
        f"{tests_info}"
        f"{exec_info}\n"
        "Find problems."
    )
    payload = await client.complete_json_object(
        system=_ADVERSARIAL_SYSTEM_PROMPT,
        user=user,
        max_tokens=max_tokens,
        temperature=0.0,
    )
    return AdversarialReview.model_validate(payload)

