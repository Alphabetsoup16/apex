from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from apex.safety.redaction import redact_secrets
from apex.safety.validators import extract_first_json_object


@dataclass(frozen=True)
class BedrockConverseConfig:
    """AWS Bedrock Runtime ``converse`` (sync boto3 wrapped in ``asyncio.to_thread``)."""

    model_id: str
    region: str | None = None


class BedrockConverseClient:
    def __init__(self, config: BedrockConverseConfig) -> None:
        try:
            import boto3  # type: ignore[import-untyped]
        except ImportError as e:
            raise RuntimeError(
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
        parse_err: Exception | None = None
        u = user
        budget = 3
        for attempt in range(budget):
            text = await self.complete_text(
                system=sys_json,
                user=u,
                max_tokens=max_tokens,
                temperature=(0.0 if attempt > 0 else temperature),
            )
            try:
                return json.loads(extract_first_json_object(text))
            except asyncio.CancelledError:
                raise
            except (json.JSONDecodeError, ValueError, TypeError, KeyError) as e:
                parse_err = e
                u = (
                    user
                    + "\n\nIMPORTANT: Your previous output was not valid JSON. "
                    + "Output ONLY a single valid JSON object and nothing else."
                )
        raise RuntimeError(f"Failed to obtain valid JSON from Bedrock: {parse_err}") from parse_err
