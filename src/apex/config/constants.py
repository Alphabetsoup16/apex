from __future__ import annotations

# Baseline similarity is a conservative string similarity heuristic used to avoid
# over-trusting a "high_verified" outcome when an answer drifts too far from a
# known-good baseline.
#
# If you adjust this, update any documentation/tests that mention the threshold.
BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD: float = 0.8

# Minimum ensemble convergence (0–1) required for ``high_verified`` when other
# signals allow it. Used by ``apex.scoring.decide_verdict``.
HIGH_VERIFIED_CONVERGENCE_THRESHOLD: float = 0.98

# Below ``HIGH_VERIFIED_CONVERGENCE_THRESHOLD`` but at or above this → ``moderate`` band
# in ``metadata.uncertainty`` (``apex.pipeline.observability``).
CONVERGENCE_MODERATE_THRESHOLD: float = 0.85

# When scoring text variants, weight of answer-string similarity vs key-claim
# similarity (pairwise convergence and best-candidate selection). Must sum to 1.0.
TEXT_ANSWER_CONVERGENCE_WEIGHT: float = 0.7
TEXT_CLAIMS_CONVERGENCE_WEIGHT: float = 0.3

# ``apex_run`` clamps ``ensemble_runs`` to this inclusive range (see tool docs).
ENSEMBLE_RUNS_MIN_EFFECTIVE: int = 2
ENSEMBLE_RUNS_MAX_EFFECTIVE: int = 3
