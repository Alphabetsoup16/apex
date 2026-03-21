from __future__ import annotations

from apex.config.constants import MCP_MAX_SUPPLEMENTARY_CONTEXT_CHARS
from apex.llm.interface import LLMClient
from apex.models import AdversarialReview, CodeSolution

_INSPECTION_SYSTEM_PROMPT = """\
You are a documentation-based code inspector.

Your job is to detect correctness risks and spec violations in the candidate code.
You are NOT executing code.

Return ONLY valid JSON with this schema:
{
  "findings": [
    {
      "severity": "high" | "medium" | "low",
      "type": "string category",
      "confidence": 0.0,
      "evidence": "verbatim mismatch evidence or explanation",
      "location": "optional",
      "recommendation": "optional"
    }
  ]
}

Rules:
- Output JSON only (no markdown).
- If there are no meaningful issues, return {"findings": []}.
- Use "high" only for issues that are likely to cause functional failure, build/test failure,
  or clear safety/correctness violations.
"""


def _truncate(s: str, *, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "\n\n[TRUNCATED]"


async def inspect_code_doc_only(
    *,
    client: LLMClient,
    task_prompt: str,
    candidate: CodeSolution,
    tests_files_by_suite: list[list[dict]] | None,
    execution_passes: list[bool | None] | None,
    max_tokens: int,
    language: str | None = None,
    diff: str | None = None,
    repo_conventions: str | None = None,
    supplementary_context: str | None = None,
) -> AdversarialReview:
    solution_files = "\n".join([f"--- {f.path} ---\n{f.content}" for f in candidate.files])

    tests_info = ""
    if tests_files_by_suite is not None:
        suite_sections: list[str] = []
        for idx, suite in enumerate(tests_files_by_suite):
            joined = "\n".join([f"--- {f['path']} ---\n{f['content']}" for f in suite])
            suite_sections.append(f"\nCandidate tests suite {idx}:\n{joined}")
        tests_info = "\n\n" + "\n".join(suite_sections).strip()

    exec_info = ""
    if execution_passes is not None:
        lines = []
        for idx, passed in enumerate(execution_passes):
            lines.append(f"- suite {idx}: pass={passed}")
        exec_info = "\n\nExecution results (if available):\n" + "\n".join(lines) + "\n"

    diff_info = ""
    if diff:
        diff_info = "\n\nDiff:\n" + _truncate(diff, max_chars=12000)
        solution_files = _truncate(solution_files, max_chars=6000)
    else:
        solution_files = _truncate(solution_files, max_chars=20000)

    tests_info = _truncate(tests_info, max_chars=12000)

    supp = ""
    if supplementary_context:
        supp = (
            f"Supplementary context (operator-provided, may include repo notes or static "
            f"snippets — not live index/RAG):\n"
            f"{_truncate(supplementary_context, max_chars=MCP_MAX_SUPPLEMENTARY_CONTEXT_CHARS)}\n\n"
        )

    user = (
        (f"Language:\n{language}\n\n" if language else "")
        + (
            f"Repo conventions:\n{_truncate(repo_conventions, max_chars=2000)}\n\n"
            if repo_conventions
            else ""
        )
        + supp
        + f"Task requirements:\n{task_prompt}\n\n"
        + f"Candidate code (may be truncated):\n{solution_files}"
        f"{tests_info}"
        f"{exec_info}\n"
        f"{diff_info}"
        "Inspect for correctness risks and spec violations. Return ONLY the JSON findings."
    )

    payload = await client.complete_json_object(
        system=_INSPECTION_SYSTEM_PROMPT,
        user=user,
        max_tokens=max_tokens,
        temperature=0.0,
    )
    return AdversarialReview.model_validate(payload)
