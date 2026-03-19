# Tool Interface Contract (`apex.run`)

APEX exposes a single MCP tool: `apex.run`.

## Inputs

- `prompt` (string)
- `mode` (`auto` | `text` | `code`, default: `auto`)
  - `auto` infers `text` vs `code` from the prompt
- `code_ground_truth` (boolean, default: `false`)
  - only applies when `mode=code`
- `ensemble_runs` (int, default: `3`)
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
- `adversarial_review`: object | `null`
- `execution`: object | `null` (code-mode execution result, when available)

### Metadata notes

- `metadata.pipeline_steps`: ordered traces for steps executed via the standard runner (see [pipeline-steps.md](pipeline-steps.md)); includes at least `cot_audit`.
- If `known_good_baseline` is provided, `metadata.baseline_similarity` may be included.
- If chain-of-thought leakage is detected, the run is `blocked` and `metadata.cot_audit` is included.

