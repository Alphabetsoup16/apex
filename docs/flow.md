# Flow

**Map only** — canonical step IDs and order live in **`metadata.pipeline_steps`**. See [pipeline-steps.md](pipeline-steps.md).

```mermaid
flowchart TD
  A["MCP: apex.run"] --> B["apex.pipeline.run.apex_run"]

  B --> C{mode}
  C -->|text| T1["Ensemble: N text variants"]
  T1 --> T2["Convergence → select best"]
  T2 --> T3["CoT audit (block on leakage)"]
  T3 --> T4["Adversarial review"]
  T4 --> V_TEXT["Verdict (decide_verdict)"]

  C -->|code| C1["Ensemble: N code variants"]
  C1 --> C2["Convergence → select best"]
  C2 --> C3["CoT audit on solution"]
  C3 --> C4{code_ground_truth?}
  C4 -->|yes| C5["tests_v1; tests_v2 in parallel with v1"]
  C5 --> C6["Validate bundles"]
  C6 --> C7["Execute both suites (parallel)"]
  C4 -->|no| C8["tests_v1 only"]
  C8 --> C9["Validate bundles"]
  C7 --> C10["Adversarial review + doc inspection (parallel)"]
  C9 --> C10
  C10 --> C10b["Findings policy (high/medium retained)"]
  C10b --> C11{inspection high?}
  C11 -->|yes| C12["Fold inspection as adversarial_high"]
  C11 -->|no| C13["No inspection-only block"]
  C12 --> V_CODE["Verdict (GT: execution gates high_verified)"]
  C13 --> V_CODE

  V_TEXT --> BL{known_good_baseline?}
  V_CODE --> BL
  BL -->|yes| BL_CMP["Baseline similarity → may downgrade high_verified"]
  BL -->|no| BL_SKIP["Skip (optional trace)"]
  BL_CMP --> OUTA["Result: verdict, output, pipeline_steps"]
  BL_SKIP --> OUTA

  OUTA --> FIN["finalize_run_result"]
  FIN --> LED["Ledger (if enabled)"]
  LED --> RET["Response JSON"]
```

**Constraints:** `ensemble_runs` clamped **2–3** (`apex.config.constants`). **Code, no ground truth:** no execution; steps still traced.

**Post-run:** `finalize_run_result` adds **`telemetry`** / **`uncertainty`**; SQLite ledger unless **`APEX_LEDGER_DISABLED=1`**. [pipeline-steps.md#observability-automatic](pipeline-steps.md#observability-automatic) · [configuration.md#run-ledger-sqlite](configuration.md#run-ledger-sqlite) · **`apex ledger summary`**.
