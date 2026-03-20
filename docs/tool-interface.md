# Tool Interface Contract (`apex.run`)

APEX exposes a single MCP tool: `apex.run`.

## Inputs

- `prompt` (string)
- `mode` (`auto` | `text` | `code`, default: `auto`)
  - `auto` infers `text` vs `code` from a **small keyword heuristic** on the prompt. It can misclassify unusual prompts; use an explicit `mode` when the outcome must be deterministic.
- `code_ground_truth` (boolean, default: `false`)
  - only applies when `mode=code`
- `ensemble_runs` (int, default: `3`)
  - **Clamped** server-side to the inclusive range **2–3** (see `ENSEMBLE_RUNS_MIN_EFFECTIVE` / `ENSEMBLE_RUNS_MAX_EFFECTIVE` in `apex.config.constants`). Metadata includes `ensemble_runs_requested` and `ensemble_runs_effective` on successful runs; top-level failure metadata includes the same fields.
- `max_tokens` (int, default: `1024`)
- `known_good_baseline` (string | null, optional)
  - if provided, APEX can downgrade `high_verified` when output divergence is large
- `language` (string | null, optional)
- `diff` (string | null, optional)
- `repo_conventions` (string | null, optional)
- `output_mode` (string, default: `candidate`)
  - `candidate`: return the best candidate output (current default behavior)
  - `review_pack`: return a PR review pack synthesized from findings

## Output fields

The tool returns JSON shaped like:

- `verdict`: `high_verified` | `needs_review` | `blocked`
- `output`: string (best candidate answer, or concatenated code bundle)
- `metadata`: object (structured run metadata)
- `adversarial_review`: object | `null` (post–findings-policy view; **`high` / `medium` are never removed** by policy — see [configuration.md](configuration.md))
- `execution`: object | `null` (code-mode execution result, when available)

### Metadata notes

- **`telemetry`** (`schema`: `apex.telemetry/v1`), added by `finalize_run_result`:
  - **`trace_id`**, **`root_span_id`**: correlation / exporter-friendly IDs.
  - **`run_wall_ms`**: from **`timings_ms.total`** when it is a numeric **`int`** or **`float`** (rounded); otherwise **`null`**.
  - **`spans[]`**: one synthetic span per **`pipeline_steps`** row (`name` = step `id`, plus duration, `ok`, `detail`).
  - **`trace_validation`**: always present — `{ "ok": bool, "issues": string[] }`. Non-empty **`issues`** means the step list failed contract checks (see [pipeline-steps.md](pipeline-steps.md#trace-contract-validated)); the run still returns normally so operators can alert on **`telemetry.trace_validation.ok`**.
- **`uncertainty`** (`schema`: `apex.uncertainty/v1`): `convergence`, `convergence_band` (`strong` / `moderate` / `weak` / `unknown`), `ensemble_divergence_hint` (roughly `1 - convergence` when known), adversarial + code-inspection summaries, and **`execution_surface`** for code + ground-truth runs.
- `ensemble_runs_requested` / `ensemble_runs_effective`: tool input vs value used after clamping (successful runs).
- If the run aborts inside `apex_run` before a mode-specific pipeline result is returned (e.g. missing LLM config), `verdict` is `blocked` and metadata includes `error_type`, full `error` string, `mode`, `mode_request`, `mode_inferred` (when `mode=auto`), `timings_ms.total` (wall time including client setup), and an empty `pipeline_steps` list.
- `metadata.pipeline_steps`: ordered traces for pipeline stages (see [pipeline-steps.md](pipeline-steps.md)); includes `ensemble`, `cot_audit`, and mode-specific follow-on steps (or explicit skip rows for optional stages).
- If `known_good_baseline` is provided, `metadata.baseline_similarity` may be included.
- If chain-of-thought leakage is detected, the run is `blocked` and `metadata.cot_audit` is included.

