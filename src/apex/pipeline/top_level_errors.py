"""Stable ``error_code`` strings for tool results; renames are API-breaking (see docs)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
from pydantic import ValidationError as PydanticValidationError

from apex.code_ground_truth.executor_client import ExecutionBackendError
from apex.config.env import env_bool
from apex.config.errors import ApexConfigurationError

APEX_CONFIGURATION = "apex.configuration"
APEX_VALIDATION = "apex.validation"
APEX_IO = "apex.io"
APEX_NETWORK = "apex.network"
APEX_EXECUTION_BACKEND = "apex.execution_backend"
APEX_INTERNAL = "apex.internal"
APEX_CAPACITY = "apex.capacity"
APEX_RUN_TIMEOUT = "apex.run_timeout"
APEX_CANCELLED = "apex.cancelled"
APEX_MCP_CORRELATION = "apex.mcp.correlation"

_SANITIZED: dict[str, str] = {
    APEX_CONFIGURATION: (
        "APEX configuration is missing or invalid. "
        "Set required environment variables or run `apex init`."
    ),
    APEX_VALIDATION: "Validation failed for generated or supplied artifacts.",
    APEX_IO: "A file or storage operation failed.",
    APEX_NETWORK: "A network request to an external service failed.",
    APEX_EXECUTION_BACKEND: "The code execution backend reported an error.",
    APEX_INTERNAL: "An unexpected error occurred during the run.",
    APEX_CAPACITY: "Too many concurrent APEX runs; try again shortly.",
    APEX_RUN_TIMEOUT: "The run exceeded its maximum wall-clock time.",
    APEX_CANCELLED: "The run was cancelled before completion.",
    APEX_MCP_CORRELATION: "correlation_id is invalid or already in use by an active run.",
}

_MAX_DETAIL_CHARS = 8192


def apex_sanitized_error(code: str) -> str:
    """Stable operator-facing string for a known ``error_code``."""
    return _SANITIZED.get(code, _SANITIZED[APEX_INTERNAL])


def _expose_error_details() -> bool:
    return env_bool("APEX_EXPOSE_ERROR_DETAILS", default=False)


def _walk_causes(start: BaseException | None) -> Iterator[BaseException]:
    cur = start
    seen: set[int] = set()
    while cur is not None and id(cur) not in seen:
        yield cur
        seen.add(id(cur))
        cur = cur.__cause__


def _exception_chain(exc: BaseException):
    yield from _walk_causes(exc)
    ctx = exc.__context__
    cause = exc.__cause__
    if ctx is not None and ctx is not cause:
        yield from _walk_causes(ctx)


def _chain_has_httpx(exc: BaseException) -> bool:
    return any(isinstance(e, httpx.HTTPError) for e in _exception_chain(exc))


def _is_configuration_runtime_message(msg: str) -> bool:
    needles = (
        "Missing Anthropic API key",
        "Missing Anthropic model",
        "Missing OpenAI API key",
        "Missing OpenAI model",
        "Missing Bedrock model id",
        "Unsupported LLM provider",
        "requires boto3",
        "run: apex init",
    )
    return any(n in msg for n in needles)


def classify_top_level_exception(exc: BaseException) -> tuple[str, str]:
    """
    Map an exception to (``error_code``, sanitized human ``error`` message).

    The message is safe to return to any MCP client; it must not embed host paths,
    URLs, or provider bodies.
    """
    if isinstance(exc, (ValueError, PydanticValidationError)):
        return APEX_VALIDATION, _SANITIZED[APEX_VALIDATION]
    if isinstance(exc, httpx.HTTPError):
        return APEX_NETWORK, _SANITIZED[APEX_NETWORK]
    if isinstance(exc, (OSError, PermissionError)):
        return APEX_IO, _SANITIZED[APEX_IO]
    if isinstance(exc, ExecutionBackendError):
        return APEX_EXECUTION_BACKEND, _SANITIZED[APEX_EXECUTION_BACKEND]

    if isinstance(exc, ApexConfigurationError):
        return APEX_CONFIGURATION, _SANITIZED[APEX_CONFIGURATION]

    if isinstance(exc, RuntimeError):
        msg = str(exc)
        if _is_configuration_runtime_message(msg):
            return APEX_CONFIGURATION, _SANITIZED[APEX_CONFIGURATION]
        if _chain_has_httpx(exc):
            return APEX_NETWORK, _SANITIZED[APEX_NETWORK]
        return APEX_INTERNAL, _SANITIZED[APEX_INTERNAL]

    if _chain_has_httpx(exc):
        return APEX_NETWORK, _SANITIZED[APEX_NETWORK]

    return APEX_INTERNAL, _SANITIZED[APEX_INTERNAL]


def build_top_level_error_metadata(exc: BaseException) -> dict[str, Any]:
    """
    Fields merged into ``metadata`` for top-level ``apex_run`` failures.

    - ``error_code``: stable machine-readable code
    - ``error``: sanitized string (replaces raw ``str(exc)`` for clients)
    - ``error_type``: exception class name (diagnostic; not a contract for branching)
    - ``error_detail``: raw ``str(exc)`` (truncated), only if ``APEX_EXPOSE_ERROR_DETAILS`` is set
    """
    code, message = classify_top_level_exception(exc)
    meta: dict[str, Any] = {
        "error_code": code,
        "error": message,
        "error_type": type(exc).__name__,
    }
    if _expose_error_details():
        raw = str(exc)
        if len(raw) > _MAX_DETAIL_CHARS:
            raw = raw[:_MAX_DETAIL_CHARS] + "...[truncated]"
        meta["error_detail"] = raw
    if isinstance(exc, ExecutionBackendError):
        meta["execution_backend_reason"] = exc.reason
        if exc.http_status is not None:
            meta["execution_backend_http_status"] = exc.http_status
    return meta
