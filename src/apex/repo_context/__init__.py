"""
Explicit, allowlisted read-only filesystem access for MCP clients.

No background indexing or RAG — operators pass root-relative paths and bounded globs.
"""

from __future__ import annotations

from apex.repo_context.access import (
    glob_disabled_payload,
    glob_payload,
    read_disabled_payload,
    read_file_payload,
    status_payload,
)
from apex.repo_context.config import RepoContextConfig, load_repo_context_config

__all__ = [
    "RepoContextConfig",
    "glob_disabled_payload",
    "glob_payload",
    "load_repo_context_config",
    "read_disabled_payload",
    "read_file_payload",
    "status_payload",
]
