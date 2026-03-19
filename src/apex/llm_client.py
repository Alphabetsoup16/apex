from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from apex.llm_interface import LLMClient
from apex.safety.redaction import redact_secrets
from apex.safety.validators import extract_first_json_object


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    model: str
    base_url: str = "https://api.anthropic.com"
    timeout_s: float = 60.0
    max_retries: int = 2


class AnthropicMessagesClient:
    def __init__(self, config: LLMConfig):
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
        """
        Returns the concatenated text from all `content` blocks.
        """
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
            "messages": [
                {
                    "role": "user",
                    "content": user_redacted,
                }
            ],
        }

        url = f"{self._config.base_url}/v1/messages"
        last_err: Exception | None = None
        for attempt in range(self._config.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._config.timeout_s) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                # Anthropic returns { content: [ {type:"text", text:"..."} ] }
                content_blocks = data.get("content", []) or []
                texts: list[str] = []
                for blk in content_blocks:
                    if blk.get("type") == "text" and isinstance(blk.get("text"), str):
                        texts.append(blk["text"])
                return "".join(texts).strip()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # pragma: no cover (network)
                last_err = e
                # Small backoff; don't retry for 4xx
                if isinstance(e, httpx.HTTPStatusError) and 400 <= e.response.status_code < 500:
                    break
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
        """
        Expects the model to output a single JSON object.
        """
        parse_err: Exception | None = None
        retry_budget = self._config.max_retries + 1

        for attempt in range(retry_budget):
            text = await self.complete_text(
                system=system,
                user=user,
                max_tokens=max_tokens,
                temperature=(0.0 if attempt > 0 else temperature),
            )
            try:
                # We accept wrapper text, but still require the first JSON object.
                json_str = extract_first_json_object(text)
                return json.loads(json_str)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                parse_err = e
                user = (
                    user
                    + "\n\nIMPORTANT: Your previous output was not valid JSON. "
                    + "Output ONLY a single valid JSON object and nothing else."
                )
                continue

        raise RuntimeError(f"Failed to obtain valid JSON from model: {parse_err}") from parse_err


def load_anthropic_config_from_env() -> LLMConfig:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    model = os.environ.get("ANTHROPIC_MODEL", "").strip()
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip() or "https://api.anthropic.com"
    if not api_key:
        raise RuntimeError("Missing required env var: ANTHROPIC_API_KEY")
    if not model:
        raise RuntimeError("Missing required env var: ANTHROPIC_MODEL")
    return LLMConfig(api_key=api_key, model=model, base_url=base_url)


def load_llm_client_from_env() -> LLMClient:
    """
    Provider selection. For now only Anthropic is implemented.

    Default:
      APEX_LLM_PROVIDER=anthropic
    """

    provider = os.environ.get("APEX_LLM_PROVIDER", "anthropic").strip().lower()
    if provider == "anthropic":
        return AnthropicMessagesClient(load_anthropic_config_from_env())
    raise RuntimeError(f"Unsupported LLM provider: {provider}")

