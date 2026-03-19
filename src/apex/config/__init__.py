"""
Runtime configuration: thresholds, merged conventions, optional findings policy.
"""

from apex.config.constants import BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD
from apex.config.conventions import load_effective_conventions
from apex.config.policy import FindingsPolicy, load_findings_policy

__all__ = [
    "BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD",
    "FindingsPolicy",
    "load_effective_conventions",
    "load_findings_policy",
]
