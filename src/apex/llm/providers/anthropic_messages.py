from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx

from apex.llm.json_from_text import (
    complete_json_object_via_text_attempts,
    retry_user_append_suffix,
)
from apex.safety.redaction import redact_secrets


@dataclass(frozen=True)
class AnthropicConfig:
    api_key: str
    model: str
    base_url: str = "https://api.anthropic.com"
    timeout_s: float = 60.0
    max_retries: int = 2


class AnthropicMessagesClient:
    def __init__(self, config: AnthropicConfig):
        self._config = config

    @property
    def model(self) -> str:
        return self._config.model

    async def complete_text(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        system_redacted = redact_secrets(system)
        user_redacted = redact_secrets(user)

        headers = {
            "x-api-key": self._config.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self._config.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_redacted,
            "messages": [{"role": "user", "content": user_redacted}],
        }

        url = f"{self._config.base_url}/v1/messages"
        last_err: Exception | None = None
        for attempt in range(self._config.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._config.timeout_s) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content_blocks = data.get("content", []) or []
                texts: list[str] = []
                for blk in content_blocks:
                    if blk.get("type") == "text" and isinstance(blk.get("text"), str):
                        texts.append(blk["text"])
                return "".join(texts).strip()
            except asyncio.CancelledError:
                raise
            except httpx.HTTPError as e:  # pragma: no cover (network)
                last_err = e
                if isinstance(e, httpx.HTTPStatusError) and 400 <= e.response.status_code < 500:
                    break
                if attempt < self._config.max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))
            except (json.JSONDecodeError, TypeError, KeyError, ValueError) as e:  # pragma: no cover
                last_err = e
                if attempt < self._config.max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))
        raise RuntimeError(f"Anthropic completion failed: {last_err}") from last_err

    async def complete_json_object(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        async def fetch_text(attempt: int, user_msg: str) -> str:
            return await self.complete_text(
                system=system,
                user=user_msg,
                max_tokens=max_tokens,
                temperature=(0.0 if attempt > 0 else temperature),
            )

        return await complete_json_object_via_text_attempts(
            fetch_text=fetch_text,
            initial_user=user,
            max_attempts=self._config.max_retries + 1,
            on_parse_failure_advance_user=retry_user_append_suffix,
            failure_label="model",
        )
