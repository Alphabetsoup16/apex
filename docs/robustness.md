# Robustness & architectural boundaries

This doc is the **engineering contract** for what is guaranteed vs best-effort. It complements [architecture.md](architecture.md) and [safety.md](safety.md).

## What is deliberately solid

| Area | Mechanism |
|------|-----------|
| **Layering** | Pipeline (`apex.pipeline.*`) does not import MCP. MCP is a thin adapter over `apex_run`. |
| **Single verification core** | `apex.pipeline.run.apex_run` is the only place a full run is orchestrated; input limits live in `apex.safety.run_input_limits`. |
| **Ledger isolation** | SQLite writes run in a thread; failures are swallowed so the **tool result is never lost** because of the ledger. |
| **Trace contract** | `finalize_run_result` validates `pipeline_steps` shape; issues surface under `metadata.telemetry.trace_validation` without failing the HTTP/MCP response. |
| **Top-level errors** | Uncaught exceptions become `verdict: blocked` with sanitized `error` / `error_code` (optional `error_detail` behind env). |
| **Tests without FastMCP** | `apex.mcp` package uses lazy `create_mcp_server`; submodules import without the `mcp` PyPI dependency. |
| **Ledger reads** | Parameterized SQL; read-only `file:` URIs; bounded `limit`. |
| **Repo context** | Optional MCP reads only under `APEX_REPO_CONTEXT_ROOT`; no indexer ([repo-context.md](repo-context.md)). |

## Best-effort / known limitations

| Topic | Reality |
|-------|---------|
| **LLM output** | Stochastic; JSON validation and retries are bounded by provider behavior. |
| **`mode=auto`** | Keyword heuristic only; production clients should set `mode` explicitly when classification must be deterministic. |
| **Redaction** | Heuristic, not a formal guarantee. |
| **`cancel_run`** | Cooperative (`asyncio` cancellation at `await` points), not a hard process kill. |
| **Doc inspection** | LLM-only; `supplementary_context` is static text, not a live repo index. |
| **`high_verified`** | Strong signal under documented rules, not a substitute for full CI / security review. |

## Invariants to preserve when changing code

1. **Never** let ledger I/O raise into the primary return path of `apex_run`.
2. **Never** weaken findings policy for **high** / **medium** adversarial severities ([configuration.md](configuration.md)).
3. **Keep** `finalize_run_result` on every completed tool-shaped result (including guard-path blocked) when metadata should carry `telemetry` / `uncertainty`.
4. **Prefer** adding observability (progress events, telemetry) over changing verdict semantics without docs + eval updates.

## Validation checklist (maintainers)

- `make check` (ruff + full pytest).
- After MCP contract changes: update [mcp-tools.md](mcp-tools.md) and [tool-interface.md](tool-interface.md).
- After new pipeline steps: [pipeline-steps.md](pipeline-steps.md) + `tests/eval/` where verdict order matters.
