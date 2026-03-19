# Verification Semantics

APEX produces a result by combining three signals:

1. Ensemble generation (multi-path convergence)
2. Adversarial review pass (structured findings)
3. Optional executable ground truth for code

## Verdicts

- `high_verified`
  - Text mode: only returned when the ensemble is strongly convergent and no medium adversarial findings exist.
  - Code mode: only returned when execution ground truth is enabled and both independent test suites pass.
- `needs_review`
  - Returned when signals indicate the output is plausible but not sufficiently verified (e.g., execution not enabled).
  - Also used when `known_good_baseline` indicates the candidate diverges enough from the baseline.
- `blocked`
  - Returned when extraction/validation fails.
  - Returned when safety/auditing (including chain-of-thought auditing) blocks the run.
  - Returned when adversarial findings are too severe.

## `known_good_baseline` downgrade

If `known_good_baseline` is provided, APEX computes a conservative similarity score against the candidate output.

If the preliminary verdict is `high_verified` but the baseline similarity is below:
- `BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD` (currently `0.8`)

APEX downgrades to `needs_review`.

## Inspection stage policy (code mode)

If an optional inspection pass reports findings:
- `high` findings can affect the final verdict
- `medium`/`low` findings are reported, but do not by themselves downgrade/grade the verdict

