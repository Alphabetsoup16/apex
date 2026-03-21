# Robustness & architectural boundaries

Guarantees vs best-effort ([architecture.md](architecture.md), [safety.md](safety.md)).

## What is deliberately solid

| Area | Mechanism |
|------|-----------|
| **Layering** | Pipeline (`apex.pipeline.*`) does not import MCP. MCP is a thin adapter over `apex_run`. |
| **Single verification core** | `apex.pipeline.run.apex_run` is the only place a full run is orchestrated; input limits live in `apex.safety.run_input_limits`. |
| **Ledger isolation** | SQLite writes run in a thread; failures are logged at **warning** and swallowed so the **tool result is never lost** because of the ledger. |
| **Trace contract** | `finalize_run_result` validates `pipeline_steps` shape; issues surface under `metadata.telemetry.trace_validation` without failing the HTTP/MCP response. |
| **Top-level errors** | Uncaught exceptions become `verdict: blocked` with sanitized `error` / `error_code` (optional `error_detail` behind env). |
| **Tests without FastMCP** | `apex.mcp` package uses lazy `create_mcp_server`; submodules import without the `mcp` PyPI dependency. |
| **Ledger reads** | Parameterized SQL; read-only `file:` URIs; bounded `limit`. |
| **Repo context** | Optional MCP reads only under `APEX_REPO_CONTEXT_ROOT`; no indexer ([repo-context.md](repo-context.md)). |
| **Run limits** | Env caps ([configuration.md](configuration.md)); semaphore `finally`; wall = `wait_for`. |

## Product semantics (clients)

Treat these as **contract** for how to integrate APEX, not implementation detail:

| Topic | Contract |
|-------|----------|
| **`mode=auto`** | Keyword heuristic only — **not** a classifier. Use explicit `mode` when behavior must be deterministic. |
| **`cancel_run`** | Cooperative cancellation at `await` boundaries inside `apex_run` — **not** a process kill. If `correlation_id` is reserved but the task is not bound yet, cancel is recorded and applied at bind. |
| **Secret redaction** | Best-effort string patterns before LLM calls — **not** a formal guarantee. |
| **Optional pipeline steps** | On failure, step `detail` records `error_type` and a fixed `message` token — **not** raw `str(exc)` (avoids leaking provider text into traces / ledger). |
| **`high_verified`** | Strong signal under documented rules — **not** a substitute for CI, SAST, or security review. |

## Best-effort / known limitations

| Topic | Reality |
|-------|---------|
| **LLM output** | Stochastic; JSON validation and retries are bounded by provider behavior. |
| **Doc inspection** | LLM-only; `supplementary_context` is static text, not a live repo index. |

## Invariants to preserve when changing code

1. **Never** let ledger I/O raise into the primary return path of `apex_run`.
2. **Never** weaken findings policy for **high** / **medium** adversarial severities ([configuration.md](configuration.md)).
3. **Keep** `finalize_run_result` on every completed tool-shaped result (including guard-path blocked) when metadata should carry `telemetry` / `uncertainty`.
4. **Prefer** adding observability (progress events, telemetry) over changing verdict semantics without docs + eval updates.

## Validation checklist (maintainers)

- `make check` (ruff + full pytest).
- After MCP contract changes: update [mcp-tools.md](mcp-tools.md) and [tool-interface.md](tool-interface.md).
- After new pipeline steps: [pipeline-steps.md](pipeline-steps.md) + `tests/eval/` where verdict order matters.
