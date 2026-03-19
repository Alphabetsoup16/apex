from __future__ import annotations

from typing import Any, Protocol


class LLMClient(Protocol):
    """
    Minimal interface APEX uses for LLM calls.

    Adapters should enforce:
    - JSON-only contract for `complete_json_object` (including parsing retries)
    - secret redaction for both text + JSON paths
    """

    @property
    def model(self) -> str: ...

    async def complete_text(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> str: ...

    async def complete_json_object(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]: ...
