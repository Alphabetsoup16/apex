from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from apex.code_ground_truth.backend_contract import (
    ExecutionBackendLimits,
    ExecutionBackendRequest,
    ExecutionBackendResponse,
)
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
    pass


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
            raise ExecutionBackendError(f"APEX internal request validation failed: {ve}") from ve

        payload: dict[str, Any] = request.model_dump()

        url = self._execute_url()
        max_retries = int(os.environ.get("APEX_EXECUTION_BACKEND_RETRIES", "2"))
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
                        f"Execution backend returned invalid response schema: {ve}"
                    ) from ve
                return validated
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                last_err = e
                if status in (502, 503, 504) and attempt < max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise

        raise RuntimeError(f"Execution backend failed after retries: {last_err}") from last_err


def load_execution_backend_from_env() -> HttpExecutionBackend:
    backend_url = os.environ.get("APEX_EXECUTION_BACKEND_URL", "").strip()
    if not backend_url:
        raise ExecutionBackendError(
            "APEX_EXECUTION_BACKEND_URL is not set; code-mode execution is unavailable."
        )
    api_key = os.environ.get("APEX_EXECUTION_BACKEND_API_KEY", "").strip()
    auth_header_name = (
        os.environ.get("APEX_EXECUTION_BACKEND_AUTH_HEADER", "").strip() or "Authorization"
    )
    auth_headers: dict[str, str] = {}
    if api_key:
        auth_headers[auth_header_name] = f"Bearer {api_key}"

    return HttpExecutionBackend(backend_url, auth_headers=auth_headers)
