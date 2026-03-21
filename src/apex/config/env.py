"""
Central helpers for reading process environment variables.

**Booleans — ``env_bool``:** Unset or empty → ``default``. Recognized true: ``1``, ``true``,
``yes``, ``y``, ``on``; false: ``0``, ``false``, ``no``, ``n``, ``off`` (case-insensitive).
Any other non-empty string → ``default`` (safe for typos).

**Ints — ``env_int``:** Unset, empty, or non-numeric → ``default``.

See ``docs/configuration.md`` for variable names and meaning.
"""

from __future__ import annotations

import os

_TRUTHY = frozenset({"1", "true", "yes", "y", "on"})
_FALSY = frozenset({"0", "false", "no", "n", "off"})


def env_str(name: str, default: str = "") -> str:
    """Strip surrounding whitespace; missing key → ``default``."""
    return os.environ.get(name, default).strip()


def env_str_or_none(name: str) -> str | None:
    """Strip; empty or missing → ``None`` (handy for JSON ``null`` vs empty string)."""
    v = os.environ.get(name, "").strip()
    return v if v else None


def env_bool(name: str, *, default: bool) -> bool:
    """
    Tri-state toggle with explicit true/false tokens; unknown values fall back to ``default``.

    Used for ``APEX_LEDGER_*``, ``APEX_PROGRESS_LOG``, ``APEX_EXPOSE_ERROR_DETAILS``, etc.
    """
    v = os.environ.get(name)
    if v is None:
        return default
    s = v.strip().lower()
    if not s:
        return default
    if s in _TRUTHY:
        return True
    if s in _FALSY:
        return False
    return default


def env_int(name: str, default: int) -> int:
    """Non-negative-style parsing: empty or invalid → ``default``."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_int_nonnegative_clamped(name: str, *, default: int, ceiling: int) -> int:
    """
    Same rules as ``apex.runtime.run_limits``: empty/invalid → ``default``; ``<= 0`` → ``0``;
    else ``min(value, ceiling)``.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
    except ValueError:
        return default
    if v <= 0:
        return 0
    return min(v, ceiling)


def env_positive_int_clamped(
    name: str,
    default: int,
    *,
    ceiling: int,
    floor: int = 1,
) -> int:
    """
    Repo-context style: empty/invalid → ``min(default, ceiling)``; parsed values →
    ``max(floor, min(value, ceiling))``.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return min(default, ceiling)
    try:
        v = int(raw)
    except ValueError:
        return min(default, ceiling)
    return max(floor, min(v, ceiling))
