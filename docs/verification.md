# Verification Semantics

## Scope: light vs CI

APEX is optimized for **high-leverage, low-latency** verification while you are authoring or reviewing an LLM output: convergence, structured adversarial/inspection findings, optional baseline comparison, and (if enabled) a **bounded** execution check via your backend.

**Medium/heavy assurance**—running the full repo test suite, production-like integration tests, builds, CodeQL, SonarQube, Snyk, etc.—is expected to run in your **existing CI** when code is pushed. APEX complements that by making the *human* review step sharper; it is not a substitute for org-wide CI gates.

APEX produces a result by combining:

1. Ensemble generation (multi-path convergence)
2. Structured adversarial review (and in code mode, doc-only **inspection** in parallel)
3. Optional executable ground truth for code (`code_ground_truth=true` + backend)

Exact numeric gates live in `apex.config.constants` (e.g. `HIGH_VERIFIED_CONVERGENCE_THRESHOLD`).

## Verdicts

- `high_verified`
  - **Text mode:** ensemble convergence ≥ `HIGH_VERIFIED_CONVERGENCE_THRESHOLD`, no **high** adversarial findings, no **medium** adversarial findings, extraction OK (`execution_required=false` in scoring).
  - **Code mode:** `execution_required` is always **true** in scoring, so `high_verified` requires **execution_pass is true** (both suites passed on the backend) **and** the same convergence + adversarial gates as above. With `code_ground_truth=false`, execution is not run (`execution_pass` stays unknown), so **`high_verified` is not returned** — typical outcome is `needs_review` unless blocked.
  - **Inspection (code):** only **high** inspection findings are merged into the same “high severity” signal as adversarial highs; inspection medium/low do not feed `DecisionSignals` today.
- `needs_review`
  - Default when signals are inconclusive (e.g. execution required but passes unknown, or convergence/adversarial short of `high_verified`).
  - Also used when `known_good_baseline` triggers a downgrade from `high_verified` (similarity below `BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD`).
- `blocked`
  - Extraction/validation failures, CoT audit blocks, **high** severity (adversarial or merged inspection), or failed execution when a failing pass is definitive.
  - **Top-level `apex_run` failures** (e.g. missing LLM configuration) return `blocked` with structured metadata (`error`, `error_type`, `pipeline_steps: []`) instead of raising through the MCP tool.

Returned results (including **`blocked`**) still receive **`metadata.telemetry`** and **`metadata.uncertainty`** from **`finalize_run_result`**, so you always get **`trace_validation`** for `pipeline_steps` and routing signals from **`uncertainty`**. The same exit path may also append to the **SQLite run ledger** (default **`~/.apex/ledger.sqlite3`**) unless **`APEX_LEDGER_DISABLED=1`**. See [tool-interface.md](tool-interface.md), [pipeline-steps.md](pipeline-steps.md), and [configuration.md](configuration.md#run-ledger-sqlite).

## `known_good_baseline` downgrade

If `known_good_baseline` is provided, APEX computes a conservative similarity score against the candidate output.

If the preliminary verdict is `high_verified` but the baseline similarity is below:
- `BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD` in `apex.config.constants` (currently `0.8`)

APEX downgrades to `needs_review`.

## Inspection stage policy (code mode)

After parallel LLM calls, **findings policy** may hide **low**-severity noise; **`high` and `medium` are never dropped** (see [configuration.md](configuration.md)).

For **verdict** computation:

- **High** inspection findings are combined with adversarial highs (either can drive `blocked`).
- **Medium / low** from inspection are for reporting only; **medium from the adversarial reviewer** still prevents `high_verified` (see `decide_verdict`).

