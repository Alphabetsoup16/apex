from __future__ import annotations

from typing import Any

from apex.config.env import env_str


def env_then_file_str(
    *,
    env_name: str,
    file_cfg: dict[str, Any],
    file_keys: str | tuple[str, ...],
    default: str = "",
) -> str:
    """
    Resolve a string: non-empty env wins, else first non-empty file key, else ``default``.

    ``file_keys`` may be a single key or a tuple (e.g. region: ``aws_region``, ``bedrock_region``).
    """
    v = env_str(env_name)
    if v:
        return v
    keys = (file_keys,) if isinstance(file_keys, str) else file_keys
    for k in keys:
        s = str(file_cfg.get(k) or "").strip()
        if s:
            return s
    return default


def first_file_str(
    file_cfg: dict[str, Any],
    file_keys: str | tuple[str, ...],
    *,
    default: str = "",
) -> str:
    """First non-empty value among ``file_keys`` in ``file_cfg`` (no env lookup)."""
    keys = (file_keys,) if isinstance(file_keys, str) else file_keys
    for k in keys:
        s = str(file_cfg.get(k) or "").strip()
        if s:
            return s
    return default
