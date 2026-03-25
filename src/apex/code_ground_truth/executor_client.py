from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from apex.code_ground_truth.backend_contract import (
    ExecutionBackendLimits,
    ExecutionBackendRequest,
    ExecutionBackendResponse,
)
from apex.config.env import env_int, env_str
from apex.models import CodeSolution, CodeTests, ExecutionResult


@dataclass(frozen=True)
class ExecutionLimits:
    cpu_seconds: int = 20
    memory_mb: int = 512
    wall_time_seconds: int = 60
    allow_network: bool = False
    allow_filesystem_write: bool = False
    allow_dependency_install: bool = False


class ExecutionBackendError(RuntimeError):
    """Structured execution-backend failure (config, transport, HTTP status, response schema)."""

    __slots__ = ("http_status", "reason")

    def __init__(
        self,
        message: str,
        *,
        reason: str = "internal",
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.http_status = http_status


class HttpExecutionBackend:
    def __init__(self, base_url: str, *, auth_headers: dict[str, str] | None = None):
        self._base_url = base_url.rstrip("/")
        self._auth_headers = auth_headers or {}

    def _execute_url(self) -> str:
        if self._base_url.endswith("/execute"):
            return self._base_url
        return f"{self._base_url}/execute"

    def _default_timeout_s(self, limits: ExecutionLimits) -> float:
        # Slightly above wall_time to account for container startup/teardown.
        return limits.wall_time_seconds + 10.0

    async def execute(
        self,
        *,
        run_id: str,
        solution: CodeSolution,
        tests: CodeTests,
        limits: ExecutionLimits,
    ) -> ExecutionResult:
        try:
            # Build and validate the request payload via a strict contract.
            request = ExecutionBackendRequest(
                run_id=run_id,
                files=solution.files,
                tests=tests.files,
                limits=ExecutionBackendLimits(
                    cpu_seconds=limits.cpu_seconds,
                    memory_mb=limits.memory_mb,
                    wall_time_seconds=limits.wall_time_seconds,
                    allow_network=limits.allow_network,
                    allow_filesystem_write=limits.allow_filesystem_write,
                    allow_dependency_install=limits.allow_dependency_install,
                ),
            )
        except ValidationError as ve:
            raise ExecutionBackendError(
                f"APEX internal request validation failed: {ve}",
                reason="invalid_request",
            ) from ve

        payload: dict[str, Any] = request.model_dump()

        url = self._execute_url()
        max_retries = max(0, env_int("APEX_EXECUTION_BACKEND_RETRIES", 2))
        last_err: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._default_timeout_s(limits)) as client:
                    resp = await client.post(url, json=payload, headers=self._auth_headers)
                resp.raise_for_status()
                data = resp.json()
                try:
                    validated = ExecutionBackendResponse.model_validate(data)
                except ValidationError as ve:
                    raise ExecutionBackendError(
                        f"Execution backend returned invalid response schema: {ve}",
                        reason="invalid_response",
                    ) from ve
                return validated
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                last_err = e
                if status in (502, 503, 504) and attempt < max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise ExecutionBackendError(
                    f"Execution backend HTTP {status}",
                    reason="http_error",
                    http_status=status,
                ) from e
            except httpx.RequestError as e:
                last_err = e
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise ExecutionBackendError(
                    f"Execution backend transport error: {type(e).__name__}",
                    reason="transport",
                ) from e

        raise ExecutionBackendError(
            f"Execution backend failed after retries: {last_err}",
            reason="internal",
        ) from last_err


def load_execution_backend_from_env() -> HttpExecutionBackend:
    backend_url = env_str("APEX_EXECUTION_BACKEND_URL")
    if not backend_url:
        raise ExecutionBackendError(
            "APEX_EXECUTION_BACKEND_URL is not set; code-mode execution is unavailable.",
            reason="configuration",
        )
    api_key = env_str("APEX_EXECUTION_BACKEND_API_KEY")
    auth_header_name = env_str("APEX_EXECUTION_BACKEND_AUTH_HEADER") or "Authorization"
    auth_headers: dict[str, str] = {}
    if api_key:
        auth_headers[auth_header_name] = f"Bearer {api_key}"

    return HttpExecutionBackend(backend_url, auth_headers=auth_headers)
