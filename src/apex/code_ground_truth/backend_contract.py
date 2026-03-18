from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field

from apex.models import CodeFile, ExecutionResult, StrictBaseModel


class ExecutionBackendLimits(StrictBaseModel):
    cpu_seconds: int = Field(ge=1, le=600)
    memory_mb: int = Field(ge=32, le=2_048_000)
    wall_time_seconds: int = Field(ge=1, le=600)
    allow_network: bool = False
    allow_filesystem_write: bool = False
    allow_dependency_install: bool = False


class ExecutionBackendRequest(StrictBaseModel):
    language: Literal["python"] = "python"
    run_id: str
    files: list[CodeFile]
    tests: list[CodeFile]
    limits: ExecutionBackendLimits


class ExecutionBackendResponse(ExecutionResult):
    # Optional extra fields; required fields are already enforced by ExecutionResult.
    exit_code: int | None = None
    timed_out: bool | None = None
    resource_stats: dict | None = None
    logs: str | None = None

