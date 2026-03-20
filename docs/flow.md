# APEX Flow

High-level behavior matches this chart. For **exact** stage names and order (including traced skips), use `metadata.pipeline_steps` and [pipeline-steps.md](pipeline-steps.md).

```mermaid
flowchart TD
  A["Client calls MCP tool apex.run"] --> B["apex.pipeline.run.apex_run"]

  B --> C{mode}
  C -->|text| T1["Generate N text variants (ensemble)"]
  T1 --> T2["Convergence scoring and select best"]
  T2 --> T3["CoT audit (block on leakage)"]
  T3 --> T4["Adversarial review (LLM)"]
  T4 --> T8["Verdict from signals (decide_verdict)"]
  T8 --> T5{known_good_baseline?}
  T5 -->|yes| T6["Baseline similarity; may downgrade high_verified → needs_review"]
  T5 -->|no| T7["Skip (traced as optional step)"]
  T6 --> OUTA["Assemble tool result (verdict, output, metadata.pipeline_steps)"]
  T7 --> OUTA

  C -->|code| C1["Generate N code variants (ensemble)"]
  C1 --> C2["Convergence scoring and select best"]
  C2 --> C3["CoT audit on solution (block on leakage)"]
  C3 --> C4{code_ground_truth?}
  C4 -->|yes| C5["Generate tests_v1; tests_v2 in parallel with v1"]
  C5 --> C6["Validate bundles (required files)"]
  C6 --> C7["Execute both suites on backend (parallel)"]
  C4 -->|no| C8["Generate tests_v1 only"]
  C8 --> C9["Validate bundles"]
  C7 --> C10["Adversarial review and doc-only inspection (parallel)"]
  C9 --> C10
  C10 --> C10b["Apply findings policy (high/medium never dropped)"]
  C10b --> C11{inspection high?}
  C11 -->|yes| C12["Treat as adversarial_high for verdict"]
  C11 -->|no| C13["No extra block from inspection"]
  C12 --> C14["Verdict from signals (execution affects high_verified in GT mode)"]
  C13 --> C14
  C14 --> C15{known_good_baseline?}
  C15 -->|yes| C16["Baseline similarity; may downgrade high_verified → needs_review"]
  C15 -->|no| C17["Skip (traced as optional step)"]
  C16 --> OUTA
  C17 --> OUTA

  OUTA --> FIN["finalize_run_result: validate pipeline_steps + telemetry + uncertainty"]
  FIN --> LED["SQLite run ledger append (default ~/.apex/ledger.sqlite3; opt-out APEX_LEDGER_DISABLED)"]
  LED --> RET["Return apex.run JSON to client"]
```

Chart matches current `text_mode` / `code_mode`. **`ensemble_runs`** is clamped to 2–3 (see `apex.config.constants`). With `code_ground_truth` off, execution stages are **skipped** but still appear as explicit rows in `metadata.pipeline_steps`. After the mode pipeline, every result goes through **`finalize_run_result`** (**`metadata.telemetry`** + **`metadata.uncertainty`**), then a **SQLite ledger** append (**on by default** at **`~/.apex/ledger.sqlite3`**; opt-out **`APEX_LEDGER_DISABLED=1`** — see [pipeline-steps.md](pipeline-steps.md#observability-automatic) and [configuration.md](configuration.md#run-ledger-sqlite)). Inspect locally with **`apex ledger summary`**.
