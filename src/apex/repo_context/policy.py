"""
Path confinement: relative paths only, no ``..``, reject absolute paths (incl. drive letters).
"""

from __future__ import annotations

from pathlib import Path


def is_root_relative_posix_path(rel: str) -> bool:
    """
    True if ``rel`` is non-empty, not absolute, and contains no ``..`` path segments.

    Backslashes are normalized to ``/`` before parsing.
    """
    s = rel.replace("\\", "/").strip()
    if not s:
        return False
    p = Path(s)
    if p.is_absolute():
        return False
    return ".." not in p.parts


def resolve_confined(root: Path, relative_path: str) -> Path | None:
    """
    Resolve ``relative_path`` under ``root``; return ``None`` if disallowed or outside root.

    Symlinks are followed; targets outside ``root`` (after resolve) are rejected.
    """
    if not is_root_relative_posix_path(relative_path):
        return None
    norm = relative_path.replace("\\", "/").strip()
    root_r = root.resolve()
    candidate = (root_r / norm).resolve()
    try:
        candidate.relative_to(root_r)
    except ValueError:
        return None
    return candidate
