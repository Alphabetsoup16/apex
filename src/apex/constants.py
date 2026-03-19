from __future__ import annotations

# Baseline similarity is a conservative string similarity heuristic used to avoid
# over-trusting a "high_verified" outcome when an answer drifts too far from a
# known-good baseline.
#
# If you adjust this, update any documentation/tests that mention the threshold.
BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD: float = 0.8

