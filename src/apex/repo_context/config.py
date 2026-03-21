from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from apex.config.constants import (
    REPO_CONTEXT_ABSOLUTE_MAX_FILE_BYTES,
    REPO_CONTEXT_ABSOLUTE_MAX_GLOB_RESULTS,
    REPO_CONTEXT_DEFAULT_MAX_FILE_BYTES,
    REPO_CONTEXT_DEFAULT_MAX_GLOB_RESULTS,
    REPO_CONTEXT_DEFAULT_MAX_PATTERN_LEN,
)


def _env_truthy_disabled(name: str) -> bool:
    v = os.environ.get(name, "").strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _positive_int(name: str, default: int, *, ceiling: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return min(default, ceiling)
    try:
        v = int(raw)
    except ValueError:
        return min(default, ceiling)
    return max(1, min(v, ceiling))


@dataclass(frozen=True)
class RepoContextConfig:
    """Effective policy for one allowlisted repository root on disk."""

    root: Path
    max_file_bytes: int
    max_glob_results: int
    max_pattern_len: int


def load_repo_context_config() -> RepoContextConfig | None:
    """
    Load config from env, or ``None`` if repo context is off.

    - ``APEX_REPO_CONTEXT_DISABLED=1`` → off
    - ``APEX_REPO_CONTEXT_ROOT`` empty → off
    - Optional: ``APEX_REPO_CONTEXT_MAX_FILE_BYTES``, ``APEX_REPO_CONTEXT_MAX_GLOB_RESULTS``,
      ``APEX_REPO_CONTEXT_MAX_PATTERN_LEN``
    """
    if _env_truthy_disabled("APEX_REPO_CONTEXT_DISABLED"):
        return None
    raw = os.environ.get("APEX_REPO_CONTEXT_ROOT", "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser()
    max_file = _positive_int(
        "APEX_REPO_CONTEXT_MAX_FILE_BYTES",
        REPO_CONTEXT_DEFAULT_MAX_FILE_BYTES,
        ceiling=REPO_CONTEXT_ABSOLUTE_MAX_FILE_BYTES,
    )
    max_glob = _positive_int(
        "APEX_REPO_CONTEXT_MAX_GLOB_RESULTS",
        REPO_CONTEXT_DEFAULT_MAX_GLOB_RESULTS,
        ceiling=REPO_CONTEXT_ABSOLUTE_MAX_GLOB_RESULTS,
    )
    max_pat = _positive_int(
        "APEX_REPO_CONTEXT_MAX_PATTERN_LEN",
        REPO_CONTEXT_DEFAULT_MAX_PATTERN_LEN,
        ceiling=512,
    )
    return RepoContextConfig(
        root=root,
        max_file_bytes=max_file,
        max_glob_results=max_glob,
        max_pattern_len=max_pat,
    )
