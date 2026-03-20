# Architecture

APEX is organized around a **light verification layer** (fast feedback while authoring/reviewing) and **optional** sandbox execution for code. Heavy CI stays outside this repo’s scope.

## Package layout (`src/apex/`)

| Area | Location | Responsibility |
|------|-----------|----------------|
| MCP entry | `apex.mcp.server` | FastMCP tool wiring (`create_mcp_server`) |
| CLI | `apex.__main__` | `apex serve` |
| Pipeline | `apex.pipeline.*` | `apex_run` router, text/code flows, `step_support` + `steps_catalog` |
| Models | `apex.models` | Pydantic schemas (tool I/O, findings, code bundles) |
| Config | `apex.config.*` | Thresholds (`constants`), conventions merge (`conventions`), findings policy (`policy`) |
| Generation | `apex.generation.*` | Ensemble prompts + variant generation |
| Review | `apex.review.*` | Adversarial pass, doc-only inspection, PR review pack |
| Scoring | `apex.scoring` | Convergence, selection, verdict policy |
| LLM | `apex.llm.*` | `interface` (protocol), `loader`, `providers/*` |
| Safety | `apex.safety.*` | Redaction, JSON extraction, CoT heuristics |
| Execution (optional) | `apex.code_ground_truth.*` | Backend client + JSON contract |

## Public entrypoints

- **`apex.pipeline.run.apex_run`**: MCP / CLI entry.
- **`apex.pipeline.helpers`**: `validate_code_bundles`, `infer_mode_from_prompt`, etc.
- **`apex.pipeline`**: re-exports `apex_run` from `apex.pipeline.run`.

## Why this shape

- **Pipeline** stays orchestration-only; **generation** / **review** / **scoring** are independently testable.
- **Config** is grouped so env/file policy does not sprawl across the tree.
- **MCP** is isolated from core logic so the server surface is one import.

## Pipeline steps

- **Catalog**: `apex.pipeline.steps_catalog` — human-readable `PipelineStepSpec` rows per mode (`required` vs `optional`).
- **Runner**: `apex.pipeline.step_support.run_async_step` — standard timing, `ok` convention, optional-step exception swallowing.
- **Guide**: [pipeline-steps.md](pipeline-steps.md).

Successful runs attach `metadata.pipeline_steps` with trace objects for each logical stage (ensemble, CoT audit, reviews, optional skips, etc.); see `docs/pipeline-steps.md`.

## Tests

- **Unit / integration (mocked LLM):** patch the module where a name is bound (e.g. `apex.pipeline.text_mode.generate_text_variants`), not a different import path for the same symbol.
- **Eval / regressions:** `tests/eval/` — parametrized cases asserting `verdict` and `metadata.pipeline_steps` order under deterministic fakes.

## Related docs

- [flow.md](flow.md) — high-level Mermaid chart (authoritative detail: `pipeline_steps` + [pipeline-steps.md](pipeline-steps.md)).
