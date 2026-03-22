"""
Structured **run / pipeline progress** events (document-style), not LLM token streaming.

Events are written as single-line JSON to the ``apex.progress`` logger when
``APEX_PROGRESS_LOG`` is truthy. They are for operators and UIs that want
coarse-grained progress (run boundaries, pipeline mode, step start/end).

**Contract:** ``schema`` is always ``apex.progress/v1``. The ``kind`` field is the
primary discriminator. Optional fields are omitted when ``None`` or unset.

**Non-goals:** This does not stream model tokens, partial answers, or change
verdict / scoring behavior. Ensemble and review stages still produce **final**
artifacts before decisions.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from apex.config.env import env_bool

PROGRESS_EVENT_SCHEMA = "apex.progress/v1"

_LOG = logging.getLogger("apex.progress")

RUN_START = "run_start"
CLIENT_READY = "client_ready"
PIPELINE_ENTER = "pipeline_enter"
PIPELINE_EXIT = "pipeline_exit"
STEP_START = "step_start"
STEP_END = "step_end"
FINALIZE_BEGIN = "finalize_begin"
FINALIZE_END = "finalize_end"
LEDGER_DISPATCH = "ledger_dispatch"
RUN_COMPLETE = "run_complete"
RUN_ERROR = "run_error"
RUN_REJECTED = "run_rejected"

_RUN_ID_CTX: ContextVar[str | None] = ContextVar("apex_progress_run_id", default=None)


def progress_log_enabled() -> bool:
    """True when ``APEX_PROGRESS_LOG`` is a truthy toggle (``1``, ``true``, ``on``, etc.)."""
    return env_bool("APEX_PROGRESS_LOG", default=False)


@contextmanager
def progress_run_scope(run_id: str) -> Iterator[None]:
    """
    Bind ``run_id`` for nested ``emit_progress`` calls that omit ``run_id=``.

    Use for the duration of ``apex_run`` so ``run_async_step`` can emit without
    threading identifiers through every helper.
    """
    token = _RUN_ID_CTX.set(run_id)
    try:
        yield
    finally:
        _RUN_ID_CTX.reset(token)


def current_progress_run_id() -> str | None:
    """Active run id from :func:`progress_run_scope`, if any."""
    return _RUN_ID_CTX.get()


def _json_safe_value(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        return v
    # Keep logs bounded and JSON-serializable; avoid dumping arbitrary objects.
    return str(v)


def build_progress_payload(kind: str, *, run_id: str, **extra: Any) -> dict[str, Any]:
    """
    Build the canonical on-the-wire dict. Used by tests and :func:`emit_progress`.
    """
    payload: dict[str, Any] = {
        "schema": PROGRESS_EVENT_SCHEMA,
        "kind": kind,
        "run_id": run_id,
        "ts_ms": int(time.time() * 1000),
    }
    for key, val in extra.items():
        if val is None:
            continue
        payload[key] = _json_safe_value(val)
    return payload


def emit_progress(kind: str, *, run_id: str | None = None, **extra: Any) -> None:
    """
    Emit one progress event as a JSON log line (no-op when logging is disabled).

    ``run_id`` defaults to the context set by :func:`progress_run_scope`.
    """
    if not progress_log_enabled():
        return
    rid = run_id if run_id is not None else _RUN_ID_CTX.get()
    if not rid:
        rid = ""
    payload = build_progress_payload(kind, run_id=rid, **extra)
    line = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=False)
    _LOG.info("%s", line)
