from __future__ import annotations

# Baseline similarity is a conservative string similarity heuristic used to avoid
# over-trusting a "high_verified" outcome when an answer drifts too far from a
# known-good baseline.
#
# If you adjust this, update any documentation/tests that mention the threshold.
BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD: float = 0.8

# Minimum ensemble convergence (0-1) required for ``high_verified`` when other
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

# --- MCP / HTTP-style tool input bounds (character counts on decoded str) ---
# Reject over-limit inputs at the MCP boundary so prompts cannot exhaust memory or
# bypass redaction expectations with huge blobs.
MCP_MAX_PROMPT_CHARS: int = 200_000
MCP_MAX_DIFF_CHARS: int = 150_000
MCP_MAX_REPO_CONVENTIONS_CHARS: int = 64_000
MCP_MAX_SUPPLEMENTARY_CONTEXT_CHARS: int = 48_000
MCP_MAX_KNOWN_GOOD_BASELINE_CHARS: int = 200_000
MCP_MAX_LANGUAGE_CHARS: int = 64
MCP_MAX_OUTPUT_MODE_CHARS: int = 32
MCP_CORRELATION_ID_MAX_LEN: int = 128

# Read-only ledger queries (MCP + CLI).
LEDGER_QUERY_MAX_LIMIT: int = 50

# --- Opt-in repo filesystem context (MCP ``repo_*`` tools; see docs/repo-context.md) ---
REPO_CONTEXT_DEFAULT_MAX_FILE_BYTES: int = 256_000
REPO_CONTEXT_DEFAULT_MAX_GLOB_RESULTS: int = 80
REPO_CONTEXT_DEFAULT_MAX_PATTERN_LEN: int = 256
# Hard ceiling even if env asks for more (memory guard).
REPO_CONTEXT_ABSOLUTE_MAX_FILE_BYTES: int = 5_000_000
REPO_CONTEXT_ABSOLUTE_MAX_GLOB_RESULTS: int = 500

# --- Whole-run operational limits (``apex.runtime.run_limits``) ---
RUN_LIMIT_MAX_CONCURRENT_CEILING: int = 256
# Upper bound for APEX_RUN_MAX_WALL_MS (24h).
RUN_LIMIT_MAX_WALL_MS_CEILING: int = 86_400_000
