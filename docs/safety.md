# Safety & auditing

## Run input bounds

`apex.safety.run_input_limits` rejects **NUL bytes** and **oversized** strings for **`apex_run`** (MCP `run`, and any other caller) before LLM work (`MCP_MAX_*` in `apex.config.constants`). Failures return `verdict: blocked` with `input_validation: true` (finalized + ledger-eligible like other blocked runs).

MCP-only: `correlation_id` / `cancel_run` ids are validated in `apex.mcp.input_guard` (charset + max length).

## Secret redaction

Heuristic patterns are stripped from content before it is sent to the LLM. Not a guarantee—treat as a best-effort filter.

## Chain-of-thought (CoT) audit

Deterministic check for common “thinking aloud” markers in model output:

- **Text:** `answer` + `key_claims`
- **Code:** formatted solution source

On hit: **`verdict: blocked`**, **`metadata.cot_audit`**. Tuned to **block when unsure**.

## Doc-only inspection (code mode)

Runs in parallel with adversarial review (LLM-only; no external doc fetch today). Optional **`supplementary_context`** on `run` adds operator-provided static text to the inspection prompt (bounded); it is **not** a live repo index or RAG layer.

**Verdict:** Adversarial **high** can block; **medium** blocks `high_verified`. Inspection **high** is OR’d with adversarial **high** for blocking. Inspection **medium/low** are informational for verdict (see [verification.md](verification.md)). Findings policy may drop **low** only ([configuration.md](configuration.md)).

## Run ledger on disk

Default **`~/.apex/ledger.sqlite3`** stores run summaries (and optionally step `detail`). That is **disk telemetry**, not the same as redacted-on-the-wire traffic. **`APEX_LEDGER_DISABLED=1`** to disable; **`APEX_LEDGER_STORE_STEP_DETAIL=0`** (default) avoids persisting large/sensitive step payloads. [configuration.md#run-ledger-sqlite](configuration.md#run-ledger-sqlite).
