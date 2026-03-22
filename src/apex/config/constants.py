from __future__ import annotations

# Baseline string-similarity threshold for downgrading ``high_verified`` vs ``known_good_baseline``.
BASELINE_SIMILARITY_DOWNGRADE_THRESHOLD: float = 0.8

# Ensemble convergence (0-1); used by ``decide_verdict`` and uncertainty bands.
HIGH_VERIFIED_CONVERGENCE_THRESHOLD: float = 0.98
CONVERGENCE_MODERATE_THRESHOLD: float = 0.85

# Text variant scoring weights (must sum to 1.0).
TEXT_ANSWER_CONVERGENCE_WEIGHT: float = 0.7
TEXT_CLAIMS_CONVERGENCE_WEIGHT: float = 0.3

ENSEMBLE_RUNS_MIN_EFFECTIVE: int = 2
ENSEMBLE_RUNS_MAX_EFFECTIVE: int = 3

# MCP / tool input bounds (decoded string length).
MCP_MAX_PROMPT_CHARS: int = 200_000
MCP_MAX_DIFF_CHARS: int = 150_000
MCP_MAX_REPO_CONVENTIONS_CHARS: int = 64_000
MCP_MAX_SUPPLEMENTARY_CONTEXT_CHARS: int = 48_000
MCP_MAX_KNOWN_GOOD_BASELINE_CHARS: int = 200_000
MCP_MAX_LANGUAGE_CHARS: int = 64
MCP_MAX_OUTPUT_MODE_CHARS: int = 32
MCP_CORRELATION_ID_MAX_LEN: int = 128

LEDGER_QUERY_MAX_LIMIT: int = 50

# Repo context (``repo_*`` MCP tools); see docs/repo-context.md.
REPO_CONTEXT_DEFAULT_MAX_FILE_BYTES: int = 256_000
REPO_CONTEXT_DEFAULT_MAX_GLOB_RESULTS: int = 80
REPO_CONTEXT_DEFAULT_MAX_PATTERN_LEN: int = 256
REPO_CONTEXT_ABSOLUTE_MAX_FILE_BYTES: int = 5_000_000
REPO_CONTEXT_ABSOLUTE_MAX_GLOB_RESULTS: int = 500

# Whole-run limits (``apex.runtime.run_limits``).
RUN_LIMIT_MAX_CONCURRENT_CEILING: int = 256
RUN_LIMIT_MAX_WALL_MS_CEILING: int = 86_400_000
