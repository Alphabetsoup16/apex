# Architecture

APEX is organized around a **light verification layer** (fast feedback while authoring/reviewing) and **optional** sandbox execution for code. Heavy CI (full matrix, SAST, dependency scans) stays outside this repo’s scope.

## Layout

| Area | Package / module | Responsibility |
|------|------------------|----------------|
| Entry | `apex.pipeline.run` | `apex_run`: mode routing, client + conventions, error boundary |
| Text path | `apex.pipeline.text_mode` | Ensemble → CoT audit → adversarial → baseline → verdict |
| Code path | `apex.pipeline.code_mode` | Ensemble → CoT audit → tests → optional dual-suite execution → parallel adversarial + inspection |
| Shared | `apex.pipeline.helpers` | Mode inference, bundle validation, blocked-result helper, baseline similarity |
| Stable imports | `apex.orchestrator` | Thin re-exports: `apex_run`, `validate_code_bundles`, `infer_mode_from_prompt` |
| LLM | `apex.llm.*`, `apex.llm_interface` | Provider adapter + env-based loader |
| Review | `apex.adversarial_review`, `apex.inspection_review`, `apex.review_pack` | Structured LLM review + PR pack output |
| Signals | `apex.scoring` | Convergence + verdict policy |
| Safety | `apex.safety.*` | Redaction, JSON extraction, CoT heuristics |
| Policy | `apex.policy` | Optional suppression of finding types/severities |
| Conventions | `apex.conventions` | Global + repo + per-call merge |
| Execution (optional) | `apex.code_ground_truth.*` | HTTP backend client + request/response contract |

## Why `pipeline/` exists

- **Separation of concerns:** routing (`run.py`) stays small; text vs code flows are independent files.
- **Testability:** unit tests monkeypatch the module where a dependency is bound (e.g. `apex.pipeline.text_mode.generate_text_variants`).
- **Product alignment:** optional execution is localized in `code_mode` + `code_ground_truth`, not mixed into generic orchestration.

## MCP surface

`apex.server` wires FastMCP to `apex_run` (via `apex.orchestrator` or `apex.pipeline.run`—same function).
