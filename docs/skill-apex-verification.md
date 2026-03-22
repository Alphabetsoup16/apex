# Skill: APEX verification (`run`)

**Purpose:** Instruct an MCP-capable host to call APEX for **structured verification** (ensemble + adversarial review; optional code execution). APEX does **not** plan multi-step work—the host orchestrates; APEX returns one **verdict** per invocation.

**Prerequisites:** Server running (`python3 -m apex serve --transport stdio` or equivalent). LLM configured ([configuration.md](configuration.md)). For code execution, backend URL set if using `code_ground_truth` ([code-execution.md](code-execution.md)).

## When to use

- After generating an answer or patch, you want **`high_verified` / `needs_review` / `blocked`** plus **explainable traces** (`metadata.pipeline_steps`).
- You need **operator visibility**: `health`, `describe_config`, `ledger_query` ([mcp-tools.md](mcp-tools.md)).

## Minimal tool call pattern

1. Optional: **`health`** or **`describe_config`** on session start.
2. **`run`** with at least `prompt`, `mode` (use explicit `text` or `code` when classification must be reliable; `auto` is heuristic-only).
3. Read **`verdict`**, **`output`**, and **`metadata`** (especially `pipeline_steps`, `telemetry`, `uncertainty` when present). Full contract: [tool-interface.md](tool-interface.md).

## Stateful orchestrators

- **`health.verification_contract`** should be **`apex.verify_step.v1`** — confirms “one `run` = one verification”; your runtime keeps workflow state ([integration.md](integration.md#stateful-orchestrators-verify-this-step)).
- Map **workflow step / attempt ids** to **`correlation_id`** when you need **cancel** or cross-service traceability.

## Long-running or cancellable runs

- Pass a unique **`correlation_id`** per concurrent invocation if the host may call **`cancel_run`** ([robustness.md](robustness.md#product-semantics-clients)).
- If the run returns **`blocked`** with capacity or wall-timeout fields, backoff or serialize at the host ([configuration.md](configuration.md)).

## Code mode notes

- **`code_ground_truth: true`** requires a working execution backend for strongest semantics ([verification.md](verification.md)).
- **`supplementary_context`** is for **static** inspection snippets only—not a substitute for reading the repo ([tool-interface.md](tool-interface.md)).

## Verdict cheat sheet

| Verdict | Host takeaway (short) |
|---------|-------------------------|
| `high_verified` | Strong signals; still not a substitute for full CI |
| `needs_review` | Escalate or constrain deployment |
| `blocked` | Safety, validation, execution, or top-level failure—inspect `metadata` |

## Further reading

[integration.md](integration.md) (verify-step pattern, Python `llm_client_factory`) · [flow.md](flow.md) · [safety.md](safety.md)
