"""Env-driven caps: ``APEX_MAX_CONCURRENT_RUNS``, ``APEX_RUN_MAX_WALL_MS`` (``0`` = off)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from apex.config.constants import (
    RUN_LIMIT_MAX_CONCURRENT_CEILING,
    RUN_LIMIT_MAX_WALL_MS_CEILING,
)
from apex.config.env import env_int_nonnegative_clamped


@dataclass(frozen=True)
class RunLimitSettings:
    """Effective limits after env parsing (``0`` means feature off)."""

    max_concurrent: int
    wall_ms: int


def load_run_limit_settings() -> RunLimitSettings:
    return RunLimitSettings(
        max_concurrent=env_int_nonnegative_clamped(
            "APEX_MAX_CONCURRENT_RUNS",
            default=0,
            ceiling=RUN_LIMIT_MAX_CONCURRENT_CEILING,
        ),
        wall_ms=env_int_nonnegative_clamped(
            "APEX_RUN_MAX_WALL_MS",
            default=0,
            ceiling=RUN_LIMIT_MAX_WALL_MS_CEILING,
        ),
    )


class ConcurrencyGate:
    """Immediate reject when ``_active >= limit``; pair ``try_acquire`` / ``release``."""

    __slots__ = ("_active", "_limit", "_lock")

    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        self._limit = limit
        self._active = 0
        self._lock = asyncio.Lock()

    async def try_acquire(self) -> bool:
        async with self._lock:
            if self._active >= self._limit:
                return False
            self._active += 1
            return True

    async def release(self) -> None:
        async with self._lock:
            self._active -= 1
            if self._active < 0:
                raise RuntimeError("ConcurrencyGate release without matching acquire")


_gate_singleton: ConcurrencyGate | None = None
_gate_for_limit: int = 0


def run_concurrency_gate(limit: int) -> ConcurrencyGate | None:
    """
    Shared gate for the process when ``limit >= 1``; ``None`` when unlimited.

    Recreates the gate if ``limit`` changes (e.g. tests monkeypatch env).
    """
    global _gate_singleton, _gate_for_limit
    if limit <= 0:
        return None
    if _gate_singleton is None or _gate_for_limit != limit:
        _gate_singleton = ConcurrencyGate(limit)
        _gate_for_limit = limit
    return _gate_singleton


def reset_run_gate_for_tests() -> None:
    """Test helper: drop singleton state."""
    global _gate_singleton, _gate_for_limit
    _gate_singleton = None
    _gate_for_limit = 0
