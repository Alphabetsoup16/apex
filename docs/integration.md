# Integrations (agent hosts & platforms)

APEX is designed to sit **behind MCP** as a **specialized verification worker**: one `run` invocation performs ensemble generation, adversarial review, optional code execution, and structured finalize—not multi-agent scheduling, planning, or open-ended tool loops.

For **wire-level** fields and schemas, treat [tool-interface.md](tool-interface.md) and [mcp-tools.md](mcp-tools.md) as authoritative. This page is **orientation** for teams wiring APEX into Cursor, Claude Desktop, custom orchestrators, or frameworks that expose MCP tools to models.

## Role in the stack

| Layer | Typical owner | APEX |
|-------|----------------|------|
| Planning, branching, user chat | Host / orchestrator | Out of scope |
| Calling tools, merging results | Host | Invokes MCP `run` (+ helpers) |
| Verification semantics, LLM usage, ledger row | APEX | **In scope** |

Do not expect APEX to replace **CI matrices**, dependency scanning, or your repo’s canonical test suite. Use it where you want **review-time signals** and a **stable JSON contract** ([verification.md](verification.md)).

## Protocol & process

- **Transport:** Same as any MCP server—commonly **stdio** (`python3 -m apex serve --transport stdio`). HTTP/SSE if your host supports it; see CLI help and [configuration.md](configuration.md).
- **Configuration:** LLM keys and model via env and/or `~/.apex/config.json` ([configuration.md](configuration.md)). Operator tooling should call **`describe_config`** after deploy to confirm effective settings (no secrets in responses).
- **Python embedders:** `apex.pipeline.run.apex_run(..., llm_client_factory=...)` supplies a sync `LLMClientFactory` (`() -> LLMClient`, see `apex.llm.interface`); MCP leaves it unset and uses env-backed loading.

## Discovery & readiness

| Tool | Use |
|------|-----|
| **`health`** | Liveness, versions, ledger/run-limit flags, repo-context gate, execution backend configured |
| **`describe_config`** | Effective config snapshot for debugging (keys redacted) |

Call these **before** relying on `run` in production dashboards or agent boot sequences.

## Primary surface: `run`

- **Input:** `prompt`, `mode` (`auto` \| `text` \| `code`), optional `code_ground_truth`, `ensemble_runs` (clamped **2–3**), `max_tokens`, context fields, optional `correlation_id`, optional `supplementary_context` (code mode inspection only). Full table: [tool-interface.md](tool-interface.md).
- **Output:** `verdict`, `output`, `metadata` (including **`pipeline_steps`**, telemetry, uncertainty), plus mode-specific fields. Treat **`metadata.pipeline_steps`** as the ordered trace of what executed ([flow.md](flow.md), [pipeline-steps.md](pipeline-steps.md)).

## Correlation, cancellation, and limits

- **`correlation_id`** (optional, charset `a-zA-Z0-9._-`): registers the in-flight task for **`cancel_run`** (cooperative cancel at next `await`). Semantics: [robustness.md](robustness.md).
- **Concurrency / wall clock:** Optional env caps (`APEX_MAX_CONCURRENT_RUNS`, `APEX_RUN_MAX_WALL_MS`) return **`blocked`** with structured `metadata`—hosts should surface `error_code` to users or retry policies ([configuration.md](configuration.md)).

## Multi-step workflows

Orchestration (e.g. “edit file → run tests → call APEX → open ticket”) belongs in the **host**. APEX intentionally exposes **one run = one verification result** so coordinators can:

- Aggregate many runs with their own **`correlation_id`** / trace strategy
- Query history via **`ledger_query`** ([mcp-tools.md](mcp-tools.md))

## Stateful orchestrators (“verify this step”)

For platforms that keep **workflow/session state** (e.g. managed agent runtimes, Bedrock-style orchestration), treat APEX as a **bounded verification tool**, not the session store:

| Host responsibility | APEX responsibility |
|---------------------|---------------------|
| Step graph, memory, approvals, retries | One **`run`** → `verdict`, `output`, `metadata` |
| Map step → `correlation_id` (optional) | Cooperative **`cancel_run`**, capacity / wall **`blocked`** |
| Merge results into working context | **`pipeline_steps`**, telemetry, optional **ledger** row |

**Practical wiring**

1. Boot: **`health`** — check `verification_contract` is `apex.verify_step.v1` ([mcp-tools.md](mcp-tools.md#health)).
2. Per step: build a **`prompt`** (and **`mode`**, context fields) from the host’s state; call **`run`**.
3. **Traceability:** use **`correlation_id`** = your workflow step / attempt id (charset [tool-interface.md](tool-interface.md)); use **`ledger_query`** or returned **`metadata`** for audits.
4. **Failure policy:** read **`metadata.error_code`**, **`verdict`**, **`cancelled`** — drive host retries or human review ([robustness.md](robustness.md)).
5. **Cost/latency:** each `run` triggers multiple LLM calls internally—schedule verification steps deliberately ([configuration.md](configuration.md#picking-a-model)).

## Audit & operations

- **Ledger:** Append-only SQLite by default; optional disable via env ([configuration.md](configuration.md#run-ledger-sqlite), [safety.md](safety.md)).
- **Progress:** Optional JSON lines on logger `apex.progress`—not token streaming ([progress-events.md](progress-events.md)).
- **Repo context:** Opt-in allowlisted read/glob for snippets—**not** live RAG ([repo-context.md](repo-context.md)).

## Skill-style summary

For a short, copy-friendly playbook you can embed in host docs or agent instructions, see [skill-apex-verification.md](skill-apex-verification.md).

## Related documentation

| Doc | Topic |
|-----|--------|
| [mcp-tools.md](mcp-tools.md) | All MCP tools |
| [tool-interface.md](tool-interface.md) | `run` I/O and metadata |
| [architecture.md](architecture.md) | Package layout, pipeline vs MCP |
| [robustness.md](robustness.md) | Guarantees and client invariants |
| [verification.md](verification.md) | Verdict semantics |
| [compatibility.md](compatibility.md) | Versioned `schema` tokens and change policy |
