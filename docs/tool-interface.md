# Tool interface (MCP)

The MCP server exposes **`run`** plus **operator** tools (`health`, `describe_config`, `ledger_query`, `cancel_run`). [mcp-tools.md](mcp-tools.md) · pipeline map: [flow.md](flow.md).

Inputs to **`run`** are validated by FastMCP / Pydantic; outputs are JSON-serializable. String **size / NUL** bounds are enforced inside **`apex_run`** via `apex.safety.run_input_limits` (same rules for MCP and embedders).

## `run` — inputs

| Field | Type / default | Notes |
|-------|------------------|--------|
| `prompt` | string | Required |
| `mode` | `auto` \| `text` \| `code` — default `auto` | `auto` uses a small keyword heuristic; use explicit `mode` when classification must be reliable |
| `code_ground_truth` | bool, default `false` | Only in `mode=code`; enables backend execution |
| `ensemble_runs` | int, default `3` | **Clamped to 2–3** (`ENSEMBLE_RUNS_*` in `apex.config.constants`). Metadata exposes `ensemble_runs_requested` vs `ensemble_runs_effective` |
| `max_tokens` | int, default `1024` | |
| `known_good_baseline` | string \| null | Optional; can downgrade `high_verified` if similarity to output is low (see [verification.md](verification.md)) |
| `language`, `diff`, `repo_conventions` | string \| null | Optional context |
| `output_mode` | string, default `candidate` | `candidate` = best output string; `review_pack` = synthesized review text |
| `correlation_id` | string \| null | Optional; register this invocation for `cancel_run` (charset: `a-zA-Z0-9._-`) |
| `supplementary_context` | string \| null | Optional; **code mode** doc inspection only — static snippets / notes from the operator (not live RAG) |

## `run` — outputs

| Field | Content |
|-------|---------|
| `verdict` | `high_verified` \| `needs_review` \| `blocked` |
| `output` | Answer string or formatted code bundle (or review pack) |
| `metadata` | Structured run data (below) |
| `adversarial_review` | Object or `null`; **policy never drops `high`/`medium`** ([configuration.md](configuration.md)) |
| `execution` | Object or `null` (code mode + backend) |

### `metadata` — common fields

- **`pipeline_steps`** — Ordered traces: `id`, `requirement`, `ok`, `duration_ms`, `detail`. Spec: [pipeline-steps.md](pipeline-steps.md).
- **`ensemble_runs_requested` / `ensemble_runs_effective`** — Request vs clamped value.
- **`baseline_similarity`** — Set when `known_good_baseline` was provided.
- **`cot_audit`** — Present when CoT leakage blocked the run.
- **`input_validation`** — `true` when the run was blocked by input limit checks (oversize / NUL).
- **`mcp_correlation_rejected`** — `true` when `correlation_id` was already in use.
- **`cancelled`** — `true` when the in-flight task was cooperatively cancelled.
- **`capacity_limit`** — Present when `error_code` is **`apex.capacity`** (host concurrent-run cap).
- **`run_wall_timeout_ms`** — Present when `error_code` is **`apex.run_timeout`**.

### `metadata.telemetry` (`apex.telemetry/v1`)

Added in `finalize_run_result`:

- **`trace_id` / `root_span_id`** — Correlation IDs
- **`run_wall_ms`** — From `timings_ms.total` if numeric; else `null`
- **`spans[]`** — One synthetic span per `pipeline_steps` row
- **`trace_validation`** — `{ "ok": bool, "issues": string[] }`; non-empty `issues` means the step list broke the contract (run still returns 200—use for alerts)

### `metadata.uncertainty` (`apex.uncertainty/v1`)

Derived signals: `convergence`, `convergence_band`, `ensemble_divergence_hint`, adversarial/inspection summaries, `execution_surface` (code + ground truth).

### Top-level `apex_run` failure (guard path)

If the run **crashes before** a normal pipeline result (e.g. bad config), you still get `verdict: blocked` and:

| Key | Purpose |
|-----|---------|
| `error_code` | Stable: `apex.configuration`, `apex.validation`, `apex.network`, `apex.execution_backend`, `apex.internal`, `apex.capacity`, `apex.run_timeout`, … |
| `error` | **Sanitized** message for any client |
| `error_type` | Exception class name (do not branch product logic on it) |
| `error_detail` | Only if **`APEX_EXPOSE_ERROR_DETAILS`** is set — raw message, truncated ~8k |

Also: `mode`, `mode_request`, `mode_inferred` (if `auto`), `timings_ms.total`, **`pipeline_steps`: []**.

**Pipeline `blocked` vs guard `blocked`:** Failures **inside** text/code mode (e.g. bundle validation) often return `blocked` with a **stage-specific** `metadata.error` string. Only the **guard** path above guarantees `error_code` + sanitized `error`. [configuration.md#top-level-errors-sanitized-by-default](configuration.md#top-level-errors-sanitized-by-default).

### Side effect: run ledger

By default, completed runs append to **`~/.apex/ledger.sqlite3`**. Does not change JSON shape. **`APEX_LEDGER_DISABLED=1`** or **`APEX_LEDGER_PATH`**: [configuration.md#run-ledger-sqlite](configuration.md#run-ledger-sqlite). **`apex ledger summary`** · **`apex ledger query`**.
