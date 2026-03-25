from __future__ import annotations

import asyncio

import httpx
import pytest

from apex.code_ground_truth.executor_client import (
    ExecutionBackendError,
    ExecutionLimits,
    HttpExecutionBackend,
)
from tests.fakes import sample_code_solution, sample_code_tests


def test_http_execution_backend_maps_http_status_error(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakeClient:
        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, *args: object, **kwargs: object) -> httpx.Response:
            captured["url"] = args[0] if args else kwargs.get("url")
            captured["json"] = kwargs.get("json")
            req = httpx.Request("POST", "http://exec/execute")
            resp = httpx.Response(422, request=req)
            raise httpx.HTTPStatusError("422", request=req, response=resp)

    def _client(**kwargs: object) -> _FakeClient:
        return _FakeClient()

    monkeypatch.setattr("apex.code_ground_truth.executor_client.httpx.AsyncClient", _client)

    async def run() -> None:
        be = HttpExecutionBackend("http://exec")
        await be.execute(
            run_id="r1",
            solution=sample_code_solution(),
            tests=sample_code_tests(),
            limits=ExecutionLimits(),
        )

    with pytest.raises(ExecutionBackendError) as ei:
        asyncio.run(run())
    assert ei.value.reason == "http_error"
    assert ei.value.http_status == 422
    assert captured["url"] == "http://exec/execute"
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["run_id"] == "r1"
    assert payload["language"] == "python"
    assert len(payload["files"]) == 1
    assert payload["files"][0]["path"] == "solution.py"
    assert len(payload["tests"]) == 1
    assert payload["tests"][0]["path"] == "test_solution.py"
    assert payload["limits"]["cpu_seconds"] == 20


def test_http_execution_backend_invalid_response_schema_maps_to_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeClient:
        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, *args: object, **kwargs: object) -> httpx.Response:
            req = httpx.Request("POST", "http://exec/execute")
            return httpx.Response(200, json={"not": "a valid execution payload"}, request=req)

    def _client(**kwargs: object) -> _FakeClient:
        return _FakeClient()

    monkeypatch.setattr("apex.code_ground_truth.executor_client.httpx.AsyncClient", _client)

    async def run() -> None:
        be = HttpExecutionBackend("http://exec")
        await be.execute(
            run_id="r1",
            solution=sample_code_solution(),
            tests=sample_code_tests(),
            limits=ExecutionLimits(),
        )

    with pytest.raises(ExecutionBackendError) as ei:
        asyncio.run(run())
    assert ei.value.reason == "invalid_response"


def test_http_execution_backend_maps_request_error_sync_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeClient:
        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, *args: object, **kwargs: object) -> None:
            raise httpx.ConnectError("nope", request=httpx.Request("POST", "http://exec/execute"))

    def _client(**kwargs: object) -> _FakeClient:
        return _FakeClient()

    monkeypatch.setattr("apex.code_ground_truth.executor_client.httpx.AsyncClient", _client)
    monkeypatch.setenv("APEX_EXECUTION_BACKEND_RETRIES", "0")

    async def run() -> None:
        be = HttpExecutionBackend("http://exec")
        await be.execute(
            run_id="r1",
            solution=sample_code_solution(),
            tests=sample_code_tests(),
            limits=ExecutionLimits(),
        )

    with pytest.raises(ExecutionBackendError) as ei:
        asyncio.run(run())
    assert ei.value.reason == "transport"
