from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from apex.config.errors import ApexConfigurationError
from apex.llm.json_from_text import (
    complete_json_object_via_text_attempts,
    retry_user_reset_to_base_with_suffix,
)
from apex.safety.redaction import redact_secrets


@dataclass(frozen=True)
class BedrockConverseConfig:
    """AWS Bedrock Runtime ``converse`` (sync boto3 wrapped in ``asyncio.to_thread``)."""

    model_id: str
    region: str | None = None
    max_retries: int = 2


class BedrockConverseClient:
    def __init__(self, config: BedrockConverseConfig) -> None:
        try:
            import boto3  # type: ignore[import-untyped]
        except ImportError as e:
            raise ApexConfigurationError(
                "Bedrock provider requires boto3. Install with: pip install 'apex[bedrock]'"
            ) from e
        self._config = config
        kwargs: dict[str, Any] = {}
        if config.region:
            kwargs["region_name"] = config.region
        self._client = boto3.client("bedrock-runtime", **kwargs)

    @property
    def model(self) -> str:
        return self._config.model_id

    def _converse_sync(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        resp = self._client.converse(
            modelId=self._config.model_id,
            system=[{"text": redact_secrets(system)}],
            messages=[{"role": "user", "content": [{"text": redact_secrets(user)}]}],
            inferenceConfig={
                "maxTokens": max_tokens,
                "temperature": temperature,
            },
        )
        msg = (resp.get("output") or {}).get("message") or {}
        blocks = msg.get("content") or []
        parts: list[str] = []
        for b in blocks:
            if isinstance(b, dict) and "text" in b:
                parts.append(str(b["text"]))
        text = "".join(parts).strip()
        if not text:
            raise ValueError("bedrock: empty model output")
        return text

    async def complete_text(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        return await asyncio.to_thread(
            self._converse_sync,
            system=system,
            user=user,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def complete_json_object(
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
            failure_label="Bedrock",
        )
