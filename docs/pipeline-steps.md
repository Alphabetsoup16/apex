# Pipeline steps (extending APEX)

This document is the **contract** for adding or changing verification stages.

## Concepts

- **Step**: a named unit of work in `text_mode` or `code_mode` (e.g. CoT audit, adversarial review).
- **Requirement**
  - **`required`**: failures must abort the run or block the verdict (per product rules). Uncaught exceptions propagate.
  - **`optional`**: failures are recorded in metadata and the run continues (unless you add explicit verdict logic).

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
