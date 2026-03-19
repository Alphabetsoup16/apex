from __future__ import annotations

import os

from apex.llm.interface import LLMClient
from apex.llm.providers.anthropic_messages import AnthropicConfig, AnthropicMessagesClient


def load_llm_client_from_env() -> LLMClient:
    """
    Provider selection.

    Default:
      APEX_LLM_PROVIDER=anthropic

    This module is intentionally small so adding another provider does not
    require changing the rest of APEX.
    """
    provider = os.environ.get("APEX_LLM_PROVIDER", "anthropic").strip().lower()

    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        model = os.environ.get("ANTHROPIC_MODEL", "").strip()
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip() or "https://api.anthropic.com"
        if not api_key:
            raise RuntimeError("Missing required env var: ANTHROPIC_API_KEY")
        if not model:
            raise RuntimeError("Missing required env var: ANTHROPIC_MODEL")
        return AnthropicMessagesClient(
            AnthropicConfig(api_key=api_key, model=model, base_url=base_url)
        )

    raise RuntimeError(f"Unsupported LLM provider: {provider}")
