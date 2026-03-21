"""
Track in-flight ``apex.run`` tasks by optional ``correlation_id`` for cooperative cancel.

Reservation happens **before** ``create_task`` so ``cancel_run`` never returns ``not_found`` for an
id the server has already accepted. ``asyncio.Task.cancel()`` is best-effort (``await`` boundaries).
"""

from __future__ import annotations

import asyncio
from typing import Any

from apex.config.constants import MCP_CORRELATION_ID_MAX_LEN

_lock = asyncio.Lock()
# correlation_id -> Task once bound; None = reserved slot (task not yet registered)
_registry: dict[str, asyncio.Task[Any] | None] = {}
# Cancel while reserved (no task yet); honoured in ``bind_correlation_task``.
_pending_cancel_before_bind: set[str] = set()


def active_correlation_ids() -> frozenset[str]:
    """Snapshot of ids currently reserved or bound (tests / diagnostics)."""
    return frozenset(_registry.keys())


async def reserve_correlation_slot(correlation_id: str) -> str | None:
    """
    Reserve ``correlation_id`` before starting ``apex_run``.

    Returns an error string if the id is taken or too long; else ``None``.
    """
    if len(correlation_id) > MCP_CORRELATION_ID_MAX_LEN:
        return "correlation_id exceeds maximum length"
    async with _lock:
        if correlation_id in _registry:
            return "correlation_id already in use by an active run"
        _registry[correlation_id] = None
    return None


async def bind_correlation_task(correlation_id: str, task: asyncio.Task[Any]) -> None:
    """Attach the running task; if cancel was requested during reservation, cancel immediately."""
    async with _lock:
        _registry[correlation_id] = task
        if correlation_id in _pending_cancel_before_bind:
            _pending_cancel_before_bind.discard(correlation_id)
            task.cancel()


async def unregister_correlation(correlation_id: str) -> None:
    """Remove reservation or binding (``run`` tool ``finally``)."""
    async with _lock:
        _registry.pop(correlation_id, None)
        _pending_cancel_before_bind.discard(correlation_id)


async def cancel_run_by_correlation_id(correlation_id: str) -> dict[str, Any]:
    """
    Request cancellation for the task registered under ``correlation_id``.

    Response schema: ``apex.cancel_run/v1``.
    """
    async with _lock:
        if correlation_id not in _registry:
            return {
                "schema": "apex.cancel_run/v1",
                "correlation_id": correlation_id,
                "status": "not_found",
                "detail": "No active run registered for this correlation_id.",
            }
        entry = _registry[correlation_id]
        if entry is None:
            _pending_cancel_before_bind.add(correlation_id)
            return {
                "schema": "apex.cancel_run/v1",
                "correlation_id": correlation_id,
                "status": "cancel_requested",
                "detail": (
                    "Cancellation recorded; the run will be cancelled as soon as it starts "
                    "(correlation slot was reserved)."
                ),
            }
        task = entry
    task.cancel()
    return {
        "schema": "apex.cancel_run/v1",
        "correlation_id": correlation_id,
        "status": "cancel_requested",
        "detail": (
            "Cancellation was requested; the run may still complete briefly at the next await."
        ),
    }
