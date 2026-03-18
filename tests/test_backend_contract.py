import pytest
from pydantic import ValidationError

from apex.code_ground_truth.backend_contract import (
    ExecutionBackendLimits,
    ExecutionBackendRequest,
    ExecutionBackendResponse,
)
from apex.models import CodeFile, CodeSolution, CodeTests


def test_backend_request_serializes_expected_fields():
    sol = CodeSolution(files=[CodeFile(path="solution.py", content="def f():\n    return 1\n")])
    tests = CodeTests(files=[CodeFile(path="test_solution.py", content="def test_ok():\n    assert True\n")])
    req = ExecutionBackendRequest(
        run_id="run_1",
        files=sol.files,
        tests=tests.files,
        limits=ExecutionBackendLimits(
            cpu_seconds=1,
            memory_mb=64,
            wall_time_seconds=2,
            allow_network=False,
            allow_filesystem_write=False,
            allow_dependency_install=False,
        ),
    )
    dumped = req.model_dump()
    assert dumped["language"] == "python"
    assert dumped["run_id"] == "run_1"
    assert isinstance(dumped["files"], list)
    assert isinstance(dumped["tests"], list)
    assert dumped["limits"]["allow_network"] is False


def test_backend_response_requires_duration_ms():
    with pytest.raises(ValidationError):
        ExecutionBackendResponse.model_validate(
            {
                "pass": True,
                "stdout": "ok",
                "stderr": "",
                # missing duration_ms
            }
        )


def test_backend_response_alias_pass():
    resp = ExecutionBackendResponse.model_validate(
        {"pass": True, "stdout": "ok", "stderr": "", "duration_ms": 123}
    )
    assert resp.pass_ is True

