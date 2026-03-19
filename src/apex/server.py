from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from apex.models import Mode
from apex.orchestrator import apex_run


def create_mcp_server() -> FastMCP:
    mcp = FastMCP("apex", json_response=True)

    @mcp.tool()
    async def run(
        prompt: str,
        mode: Mode = "auto",
        ensemble_runs: int = 3,
        max_tokens: int = 1024,
        code_ground_truth: bool = False,
        known_good_baseline: str | None = None,
    ):
        """
        Run APEX verification on a prompt.

        For text: returns the best candidate answer plus structured adversarial findings.
        Optional `known_good_baseline` can downgrade `high_verified` when outputs diverge.

        For code: generates a Python solution + pytest tests. If `code_ground_truth=true`,
        it executes tests via `APEX_EXECUTION_BACKEND_URL`, then returns a deterministic verdict.
        Also performs chain-of-thought auditing on generated solution content.
        """

        result = await apex_run(
            prompt=prompt,
            mode=mode,
            ensemble_runs=ensemble_runs,
            max_tokens=max_tokens,
            code_ground_truth=code_ground_truth,
            known_good_baseline=known_good_baseline,
        )
        return result.model_dump(by_alias=True)

    return mcp

