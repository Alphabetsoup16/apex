# Progress events (document streaming)

Structured **run- and step-level progress** for long `apex_run` invocations. This is **not** LLM token streaming: model output is still delivered only as part of the final tool result (and redaction rules still apply).

## Enable

Set a truthy **`APEX_PROGRESS_LOG`** (`1`, `true`, `on`, `yes`, …). When unset or empty, **no** progress lines are emitted (zero overhead in hot paths beyond a cheap env read).

## Transport

Each event is one **JSON object** logged at **INFO** on logger name **`apex.progress`**. The log message body is the JSON string (suitable for `grep` / log pipelines / `jq`).

## Schema (`apex.progress/v1`)

Every payload includes:

| Field | Type | Description |
|-------|------|-------------|
| `schema` | string | Always `apex.progress/v1` |
| `kind` | string | Event discriminator (see below) |
| `run_id` | string | UUID for the `apex_run` invocation |
| `ts_ms` | integer | Unix epoch milliseconds (best-effort ordering) |

Additional fields depend on `kind`. Values are JSON-safe scalars or stringified fallbacks — **no** raw prompts, diffs, or step `detail` blobs (those stay in the tool result / ledger policy).

## Event kinds

| `kind` | When | Typical extra fields |
|--------|------|----------------------|
| `run_start` | Start of `apex_run` | `mode_request`, `mode_effective`, `mode_inferred` (if auto), `ensemble_runs_*`, `max_tokens`, `code_ground_truth`, `output_mode` |
| `client_ready` | After LLM client load | `llm_provider` |
| `pipeline_enter` | Before text/code pipeline | `pipeline` (`text` \| `code`) |
| `step_start` | Before each `run_async_step` | `step_id`, `requirement` |
| `step_end` | After each step | `step_id`, `requirement`, `ok`, `duration_ms`; on failure `error_type` |
| `pipeline_exit` | After pipeline returns | `pipeline`, `verdict` (pre-finalize result) |
| `finalize_begin` / `finalize_end` | Around `finalize_run_result` | — |
| `ledger_dispatch` | Before ledger write attempt | `ledger_enabled` |
| `run_complete` | Successful or error-path completion | `verdict` |
| `run_error` | Top-level exception before blocked result | `error_type` (exception class name only) |

## Context

`run_id` is bound for the whole `apex_run` via an internal context scope so `run_async_step` can emit without threading IDs through every helper.

## Relationship to other metadata

- **`metadata.pipeline_steps`** — authoritative per-step trace in the tool result (see [pipeline-steps.md](pipeline-steps.md)).
- **`metadata.telemetry` / `metadata.uncertainty`** — attached at finalize (see [pipeline-steps.md#observability-automatic](pipeline-steps.md#observability-automatic)).

Progress events are **orthogonal**: they exist for live operators; they do not replace or alter verdict logic.

## Code

- `apex.observability.progress_events`
- Wired from `apex.pipeline.run` and `apex.pipeline.step_support`
