"""
Track in-flight ``apex.run`` tasks by optional ``correlation_id`` for cooperative cancel.

``asyncio.Task.cancel()`` is best-effort: cancellation propagates only at ``await``
points inside ``apex_run`` (which re-raises :class:`asyncio.CancelledError`).
"""

from __future__ import annotations

import asyncio
from typing import Any

from apex.config.constants import MCP_CORRELATION_ID_MAX_LEN

_lock = asyncio.Lock()
# Active runs only; entries removed in ``finally`` by the run tool wrapper.
_tasks: dict[str, asyncio.Task[Any]] = {}


def active_correlation_ids() -> frozenset[str]:
    """Snapshot of ids currently registered (for tests / diagnostics)."""
    return frozenset(_tasks.keys())


async def register_run_task(correlation_id: str, task: asyncio.Task[Any]) -> str | None:
    """
    Register ``task`` under ``correlation_id``.

    Returns an error message if the id is already in use, else ``None``.
    """
    if len(correlation_id) > MCP_CORRELATION_ID_MAX_LEN:
        return "correlation_id exceeds maximum length"
    async with _lock:
        if correlation_id in _tasks:
            return "correlation_id already in use by an active run"
        _tasks[correlation_id] = task
    return None


async def unregister_run_task(correlation_id: str) -> None:
    async with _lock:
        _tasks.pop(correlation_id, None)


async def cancel_run_by_correlation_id(correlation_id: str) -> dict[str, Any]:
    """
    Request cancellation for the task registered under ``correlation_id``.

    Response schema: ``apex.cancel_run/v1``.
    """
    async with _lock:
        task = _tasks.get(correlation_id)
    if task is None:
        return {
            "schema": "apex.cancel_run/v1",
            "correlation_id": correlation_id,
            "status": "not_found",
            "detail": "No active run registered for this correlation_id.",
        }
    task.cancel()
    return {
        "schema": "apex.cancel_run/v1",
        "correlation_id": correlation_id,
        "status": "cancel_requested",
        "detail": (
            "Cancellation was requested; the run may still complete briefly at the next await."
        ),
    }
