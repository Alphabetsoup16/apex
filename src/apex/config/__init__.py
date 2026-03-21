"""
Runtime configuration: thresholds, merged conventions, optional findings policy.

Environment variable parsing lives in ``apex.config.env`` (shared booleans / ints / strips).
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
