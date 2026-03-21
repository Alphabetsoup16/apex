# Pipeline steps

How to add or change stages in `text_mode` / `code_mode`.

## Terms

- **Step** — One unit of work (e.g. ensemble, CoT audit).
- **Trace** — One object in `metadata.pipeline_steps[]` with `id`, `requirement`, `ok`, `duration_ms`, `detail`.
- **`validate_pipeline_steps()`** — Non-throwing check; problems go to `metadata.telemetry.trace_validation.issues`.
- **`required` / `optional`** — `required`: failure should abort or block per your rules; uncaught exceptions bubble. `optional`: swallow in `run_async_step`, record `ok: false`, continue unless you add verdict logic.

## Trace contract

Enforced in `apex.pipeline.trace_contract` (`PipelineStepTraceDict`):

| Field | Rule |
|-------|------|
| Root | JSON array of objects |
| Each row | Keys exactly: `id`, `requirement`, `ok`, `duration_ms`, `detail` |
| `id` | String |
| `requirement` | Only **`required`** or **`optional`** |
| `ok` | Boolean |
| `duration_ms` | Integer ms |
| `detail` | Object (may be `{}`) |

## How to add a step

1. Register intent in **`steps_catalog.py`** (`PipelineStepSpec`).
2. Implement in **`text_mode.py`** or **`code_mode.py`** using **`run_async_step`** from **`step_support`** where possible.
3. Append **`trace.as_dict()`** to `pipeline_steps`. For skips, use **`skipped_step_record`**.

```python
from apex.pipeline.step_support import OPTIONAL, REQUIRED, run_async_step

async def _my_step() -> dict:
    if bad:
        return {"ok": False, "reason": "..."}
    return {"ok": True, "stats": 42}

trace = await run_async_step("my_step", REQUIRED, _my_step)
pipeline_steps.append(trace.as_dict())
```

Optional step that must not take down the run: use **`OPTIONAL`** and always continue.

## Ordering

**Code order wins.** The catalog documents names and intent only.

## Tests

Change step order or verdict wiring → extend **`tests/eval/`** so regressions show up without a live LLM.

## Diagram

[flow.md](flow.md).

## Observability (automatic)

`finalize_run_result` (`apex.pipeline.observability`):

1. **`validate_pipeline_steps`**
2. **`metadata.telemetry`** (`apex.telemetry/v1`) — `trace_id`, `root_span_id`, `run_wall_ms` (from numeric `timings_ms.total`), `spans[]` mirroring steps, `trace_validation`
3. **`metadata.uncertainty`** (`apex.uncertainty/v1`) — convergence band, adversarial/inspection summaries, `execution_surface`, etc.

Then **`record_apex_run_to_ledger_if_enabled`** may write SQLite (default **`~/.apex/ledger.sqlite3`**, **`APEX_LEDGER_DISABLED=1`** to stop). [configuration.md#run-ledger-sqlite](configuration.md#run-ledger-sqlite) · **`apex ledger summary`**.

## Live progress (optional)

Structured JSON log lines on logger **`apex.progress`** when **`APEX_PROGRESS_LOG`** is set — run boundaries, pipeline mode, and `step_start` / `step_end` around **`run_async_step`**. Not LLM token streaming; see [progress-events.md](progress-events.md).
