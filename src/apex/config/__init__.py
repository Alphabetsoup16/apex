"""
Runtime configuration: thresholds, merged conventions, optional findings policy.

- **Env parsing:** ``apex.config.env`` (shared booleans / ints / strips).
- **Versioned JSON tokens** (``schema``, ``verification_contract``): ``apex.config.contracts``
  — see ``docs/compatibility.md``.
"""

from apex.config.constants import (
    BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD,
    ENSEMBLE_RUNS_MAX_EFFECTIVE,
    ENSEMBLE_RUNS_MIN_EFFECTIVE,
    HIGH_VERIFIED_CONVERGENCE_THRESHOLD,
    TEXT_ANSWER_CONVERGENCE_WEIGHT,
    TEXT_CLAIMS_CONVERGENCE_WEIGHT,
)
from apex.config.conventions import load_effective_conventions
from apex.config.policy import FindingsPolicy, load_findings_policy

__all__ = [
    "BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD",
    "ENSEMBLE_RUNS_MAX_EFFECTIVE",
    "ENSEMBLE_RUNS_MIN_EFFECTIVE",
    "HIGH_VERIFIED_CONVERGENCE_THRESHOLD",
    "TEXT_ANSWER_CONVERGENCE_WEIGHT",
    "TEXT_CLAIMS_CONVERGENCE_WEIGHT",
    "FindingsPolicy",
    "load_effective_conventions",
    "load_findings_policy",
]
