from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from apex.llm.providers.openai_chat import OpenAIChatClient, OpenAIChatConfig


def test_openai_complete_text_strips_content(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers.get("authorization") == "Bearer k"
        body = json.loads(request.content.decode())
        assert body["model"] == "m"
        assert body["max_tokens"] == 8
        assert body["temperature"] == 0.0
        assert body["messages"][0] == {"role": "system", "content": "s"}
        assert body["messages"][1] == {"role": "user", "content": "u"}
        assert "response_format" not in body
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "  hi  "}}]},
        )

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        kwargs.setdefault("transport", transport)
        return real(**kwargs)

    monkeypatch.setattr("apex.llm.providers.openai_chat.httpx.AsyncClient", client_factory)

    async def run() -> str:
        c = OpenAIChatClient(OpenAIChatConfig(api_key="k", model="m"))
        return await c.complete_text(system="s", user="u", max_tokens=8, temperature=0.0)

    assert asyncio.run(run()) == "hi"


def test_openai_json_object_native_mode_parses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append("post")
        body = json.loads(request.content.decode())
        assert body["response_format"] == {"type": "json_object"}
        assert body["messages"][0]["role"] == "system"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"a": 1}'}}]},
        )

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        kwargs.setdefault("transport", transport)
        return real(**kwargs)

    monkeypatch.setattr("apex.llm.providers.openai_chat.httpx.AsyncClient", client_factory)

    async def run() -> dict[str, object]:
        c = OpenAIChatClient(OpenAIChatConfig(api_key="k", model="m", max_retries=0))
        return await c.complete_json_object(system="s", user="u", max_tokens=32, temperature=0.0)

    assert asyncio.run(run()) == {"a": 1}
    assert calls == ["post"]


def test_openai_json_object_http_500_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content.decode()))
        return httpx.Response(500, json={"error": "server"})

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        kwargs.setdefault("transport", transport)
        return real(**kwargs)

    monkeypatch.setattr("apex.llm.providers.openai_chat.httpx.AsyncClient", client_factory)

    async def run() -> None:
        c = OpenAIChatClient(OpenAIChatConfig(api_key="k", model="m", max_retries=0))
        await c.complete_json_object(system="s", user="u", max_tokens=32, temperature=0.0)

    with pytest.raises(httpx.HTTPStatusError) as ei:
        asyncio.run(run())
    assert ei.value.response.status_code == 500
    assert len(seen) == 1
    assert seen[0].get("response_format") == {"type": "json_object"}


def test_openai_json_object_empty_native_choices_falls_back_to_text_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Native JSON response with ``choices: []`` must not crash; text path recovers."""
    phase = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        phase["n"] += 1
        body = json.loads(request.content.decode())
        if phase["n"] == 1:
            assert body.get("response_format") == {"type": "json_object"}
            return httpx.Response(200, json={"choices": []})
        assert "response_format" not in body
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"recovered": true}'}}]},
        )

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        kwargs.setdefault("transport", transport)
        return real(**kwargs)

    monkeypatch.setattr("apex.llm.providers.openai_chat.httpx.AsyncClient", client_factory)

    async def run() -> dict[str, object]:
        c = OpenAIChatClient(OpenAIChatConfig(api_key="k", model="m", max_retries=0))
        return await c.complete_json_object(system="s", user="u", max_tokens=32, temperature=0.0)

    assert asyncio.run(run()) == {"recovered": True}
    assert phase["n"] == 2


def test_openai_json_object_400_falls_back_to_text_path(monkeypatch: pytest.MonkeyPatch) -> None:
    n = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        n["n"] += 1
        body = json.loads(request.content.decode())
        if n["n"] == 1:
            assert body.get("response_format") == {"type": "json_object"}
            return httpx.Response(400, json={"error": "unsupported"})
        assert "response_format" not in body
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
        )

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        kwargs.setdefault("transport", transport)
        return real(**kwargs)

    monkeypatch.setattr("apex.llm.providers.openai_chat.httpx.AsyncClient", client_factory)

    async def run() -> dict[str, object]:
        c = OpenAIChatClient(OpenAIChatConfig(api_key="k", model="m", max_retries=0))
        return await c.complete_json_object(system="s", user="u", max_tokens=32, temperature=0.1)

    assert asyncio.run(run()) == {"ok": True}
    assert n["n"] == 2
