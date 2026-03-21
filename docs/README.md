# Documentation index

**Diagrams:** [flow.md](flow.md) (run pipeline), [architecture.md](architecture.md#call-direction) (adapter vs core), [mcp-tools.md](mcp-tools.md) (tool groups), [verification.md](verification.md#how-a-verdict-is-built) (verdict), [pipeline-steps.md](pipeline-steps.md#observability-automatic) (finalize + ledger), [code-execution.md](code-execution.md#endpoint) (backend POST).

| Doc | What it covers |
|-----|----------------|
| [architecture.md](architecture.md) | Package layout, entrypoints, how pieces fit |
| [flow.md](flow.md) | Mermaid flow; read `metadata.pipeline_steps` for exact order |
| [pipeline-steps.md](pipeline-steps.md) | Adding stages, trace contract, observability |
| [progress-events.md](progress-events.md) | Optional `APEX_PROGRESS_LOG` JSON progress (not token streaming) |
| [tool-interface.md](tool-interface.md) | MCP `run` inputs/outputs, metadata fields |
| [mcp-tools.md](mcp-tools.md) | All MCP tools (`health`, ledger query, cancel, …) |
| [robustness.md](robustness.md) | Guarantees vs best-effort; invariants for contributors |
| [repo-context.md](repo-context.md) | Opt-in MCP repo read/glob (no RAG) |
| [verification.md](verification.md) | Verdict rules, baseline downgrade |
| [code-execution.md](code-execution.md) | Execution backend HTTP contract |
| [safety.md](safety.md) | Redaction, CoT audit, ledger on disk |
| [configuration.md](configuration.md) | Env vars, config file, ledger, errors |

## Where tests live

- **`tests/`** — Unit/integration; patch the module under test (see [architecture.md](architecture.md)).
- **`tests/eval/`** — Verdict + ordered `pipeline_steps` ids under fakes.
- **`tests/test_observability.py`** — Trace contract, telemetry helpers.
- **`tests/test_progress_events.py`** — Progress event schema + `run_async_step` hooks.
- **`tests/test_mcp_input_guard.py`**, **`tests/test_mcp_run_registry.py`** (reserve/bind cancel semantics), **`tests/test_mcp_diagnostics.py`** — MCP helpers (no FastMCP import).
- **`tests/test_guard_metadata.py`** — Ensemble clamp + blocked metadata shape shared by MCP / ``apex_run``.
- **`tests/test_mcp_server_wiring.py`** — With `mcp` installed (`pip install -e .`), asserts all expected tools are registered; otherwise **skipped**.
- **`tests/test_ledger_read.py`** — `read_ledger_snapshot` API.
- **`tests/test_resolve_run_modes.py`** — Shared mode resolution helper.
- **`tests/test_runtime_run_limits.py`** — Concurrency gate + wall timeout on `apex_run`.
- **`tests/test_ledger.py`** — SQLite ledger; **`tests/conftest.py`** sets `APEX_LEDGER_DISABLED=1` so the default DB is not written unless a test clears it.
- **`tests/test_top_level_errors.py`** — `error_code` / `APEX_EXPOSE_ERROR_DETAILS` (with cases in `test_pipeline_run.py`).
