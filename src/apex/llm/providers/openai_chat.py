from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx

from apex.llm.json_from_text import (
    complete_json_object_via_text_attempts,
    retry_user_reset_to_base_with_suffix,
)
from apex.safety.redaction import redact_secrets
from apex.safety.validators import extract_first_json_object


@dataclass(frozen=True)
class OpenAIChatConfig:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    timeout_s: float = 60.0
    max_retries: int = 2


class OpenAIChatClient:
    """OpenAI Chat Completions API (`/v1/chat/completions`)."""

    def __init__(self, config: OpenAIChatConfig) -> None:
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
            "authorization": f"Bearer {self._config.api_key}",
            "content-type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system_redacted},
                {"role": "user", "content": user_redacted},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        url = f"{self._config.base_url.rstrip('/')}/chat/completions"
        last_err: Exception | None = None
        for attempt in range(self._config.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._config.timeout_s) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    raise ValueError("openai: empty choices")
                msg = choices[0].get("message") or {}
                content = msg.get("content")
                if not isinstance(content, str):
                    raise ValueError("openai: missing string content")
                return content.strip()
            except asyncio.CancelledError:
                raise
            except httpx.HTTPError as e:
                last_err = e
                if isinstance(e, httpx.HTTPStatusError) and 400 <= e.response.status_code < 500:
                    break
                if attempt < self._config.max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))
            except (json.JSONDecodeError, TypeError, KeyError, ValueError) as e:
                last_err = e
                if attempt < self._config.max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))
        raise RuntimeError(f"OpenAI completion failed: {last_err}") from last_err

    async def complete_json_object(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        """Prefer ``response_format: json_object``; fall back to text extraction if unsupported."""
        try:
            return await self._post_chat_json_object(
                system=system, user=user, max_tokens=max_tokens, temperature=temperature
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                return await self._json_via_text_extraction(
                    system=system, user=user, max_tokens=max_tokens, temperature=temperature
                )
            raise
        except (ValueError, json.JSONDecodeError, TypeError, KeyError):
            return await self._json_via_text_extraction(
                system=system, user=user, max_tokens=max_tokens, temperature=temperature
            )

    async def _post_chat_json_object(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        headers = {
            "authorization": f"Bearer {self._config.api_key}",
            "content-type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": redact_secrets(system)},
                {"role": "user", "content": redact_secrets(user)},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        url = f"{self._config.base_url.rstrip('/')}/chat/completions"
        async with httpx.AsyncClient(timeout=self._config.timeout_s) as client:
            resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("openai: empty choices")
        content = (choices[0].get("message") or {}).get("content")
        if not isinstance(content, str):
            raise ValueError("openai: missing content")
        return json.loads(extract_first_json_object(content))

    async def _json_via_text_extraction(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        sys_json = system + "\n\nRespond with a single JSON object only."

        async def fetch_text(attempt: int, user_msg: str) -> str:
            return await self.complete_text(
                system=sys_json,
                user=user_msg,
                max_tokens=max_tokens,
                temperature=(0.0 if attempt > 0 else temperature),
            )

        return await complete_json_object_via_text_attempts(
            fetch_text=fetch_text,
            initial_user=user,
            max_attempts=self._config.max_retries + 1,
            on_parse_failure_advance_user=retry_user_reset_to_base_with_suffix,
            failure_label="OpenAI",
        )
