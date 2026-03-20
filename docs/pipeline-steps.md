# Pipeline steps (extending APEX)

This document is the **contract** for adding or changing verification stages.

## Concepts

- **Step**: a named unit of work in `text_mode` or `code_mode` (e.g. CoT audit, adversarial review).
- **Trace shape**: each `pipeline_steps[]` row must match the contract below. `apex.pipeline.trace_contract.validate_pipeline_steps()` checks it (non-throwing); issues are listed under `metadata.telemetry.trace_validation.issues`.
- **Requirement**
  - **`required`**: failures must abort the run or block the verdict (per product rules). Uncaught exceptions propagate.
  - **`optional`**: failures are recorded in metadata and the run continues (unless you add explicit verdict logic).

## Trace contract (validated)

`validate_pipeline_steps()` enforces (see `apex.pipeline.trace_contract`):

- `pipeline_steps` must be a **JSON array** of **objects**.
- Each row must include exactly these keys: `id`, `requirement`, `ok`, `duration_ms`, `detail` (see `PIPELINE_STEP_REQUIRED_KEYS`).
- **`id`**: string (stage identifier).
- **`requirement`**: **only** the literals **`required`** or **`optional`** (no synonyms).
- **`ok`**: boolean.
- **`duration_ms`**: integer (milliseconds).
- **`detail`**: object (may be `{}`).

Typed reference: `PipelineStepTraceDict`. Any mismatch yields human-readable issue strings; **`trace_validation.ok`** is false until the list is clean.

## Standard mechanism

1. **Register** the step in `src/apex/pipeline/steps_catalog.py`:
   - Add a `PipelineStepSpec` with `id`, `requirement`, `modes`, `summary`, and `verdict_impact`.
   - Keep this aligned with the real implementation.

2. **Implement** in `text_mode.py` or `code_mode.py`:
   - Prefer `run_async_step()` from `apex.pipeline.step_support` for async work so timing and optional/required error behavior stay consistent.
   - Your async worker returns a `dict` that may include `ok: bool` (default `True`). Other keys go into trace `detail`.

3. **Record** traces in `metadata["pipeline_steps"]`:
   - Append `trace.as_dict()` for each step that uses `run_async_step`.
   - For synchronous-only steps, you may append a hand-built dict with the same shape: `id`, `requirement`, `ok`, `duration_ms`, `detail`.
   - For stages skipped by configuration, prefer `skipped_step_record()` from `step_support` so optional steps still appear in order with `detail.skipped` / a short `reason`.

## Example (pattern)

```python
from apex.pipeline.step_support import OPTIONAL, REQUIRED, run_async_step

pipeline_steps: list[dict] = []

async def _my_step() -> dict:
    # ... work ...
    if bad:
        return {"ok": False, "reason": "..."}
    return {"ok": True, "stats": 42}

trace = await run_async_step("my_step", REQUIRED, _my_step)
pipeline_steps.append(trace.as_dict())
if not trace.ok:
    return blocked_run_result(..., extra_metadata={"pipeline_steps": pipeline_steps})
```

For an **optional** step that should never take down the run:

```python
trace = await run_async_step("extra_analyzer", OPTIONAL, _maybe_flaky)
pipeline_steps.append(trace.as_dict())
# Always continue; inspect trace.ok / trace.detail in metadata
```

## Reference catalog

Runtime listing (for docs/tests): `apex.pipeline.steps_catalog.catalog_summary()`.

## Ordering

Order is defined by the control flow in `text_mode` / `code_mode`, not by the catalog. The catalog documents intent; the code is authoritative.

## Regression checks

Add or extend cases under `tests/eval/` when you change step order or verdict behavior, so CI catches orchestration drift without a live LLM.

## High-level diagram

See [flow.md](flow.md) for a Mermaid overview (use `metadata.pipeline_steps` for exact runtime order).

## Observability (automatic)

Every `apex_run` exit path that returns an `ApexRunToolResult` goes through **`finalize_run_result`** (`apex.pipeline.observability`), which:

1. Runs **`validate_pipeline_steps`** on `metadata.pipeline_steps`.
2. Attaches **`metadata.telemetry`** and **`metadata.uncertainty`**.
3. Then **`record_apex_run_to_ledger_if_enabled`** (`apex.ledger`) may append a row to a local **SQLite** database (default **`~/.apex/ledger.sqlite3`**; disable with **`APEX_LEDGER_DISABLED=1`**). The ledger stores verdict, trace-validation summary, step timing/shape, and optionally step `detail` — see [configuration.md](configuration.md#run-ledger-sqlite). CLI: **`apex ledger summary`**.

### `metadata.telemetry` (`apex.telemetry/v1`)

- **`schema`**, **`run_id`**: identifiers for this result.
- **`trace_id`** / **`root_span_id`**: W3C-style hex IDs for correlation / OTel export.
- **`run_wall_ms`**: wall-clock duration in ms when **`metadata.timings_ms.total`** is present and numeric (**`int`** or **`float`**, rounded to int). Omitted as **`null`** if missing or not a number (booleans are ignored so `True`/`False` are never treated as milliseconds).
- **`spans[]`**: one entry per `pipeline_steps` row (synthetic `span_id`, `parent_span_id`, `name` from step `id`, `duration_ms`, `ok`, `detail`).
- **`trace_validation`**: `{ "ok": bool, "issues": string[] }` — empty `issues` means the trace list matched the contract above.

### `metadata.uncertainty` (`apex.uncertainty/v1`)

- Convergence value/band, ensemble divergence hint, adversarial counts/severity, code-inspection summaries (code mode), and **`execution_surface`**: `not_applicable` | `disabled` | `pass` | `fail` | `inconclusive`.
