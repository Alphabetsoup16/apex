from __future__ import annotations

import os

from apex.llm.interface import LLMClient
from apex.llm.providers.anthropic_messages import AnthropicConfig, AnthropicMessagesClient
from apex.llm.user_config import DEFAULT_ANTHROPIC_BASE_URL, load_user_llm_config


def load_llm_client_from_env() -> LLMClient:
    """
    Load an ``LLMClient`` from the environment and/or user config file.

    **Precedence (highest first):** environment variables, then ``~/.apex/config.json``
    (unless ``APEX_USER_CONFIG_PATH`` is set). This keeps CI and production on pure env
    while local devs can run ``apex init`` (or ``apex setup``).

    Default provider: ``anthropic`` (``APEX_LLM_PROVIDER``).
    """
    file_cfg = load_user_llm_config()

    provider = os.environ.get("APEX_LLM_PROVIDER", "").strip().lower()
    if not provider:
        provider = str(file_cfg.get("provider") or "anthropic").strip().lower() or "anthropic"

    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            api_key = str(file_cfg.get("anthropic_api_key") or "").strip()

        model = os.environ.get("ANTHROPIC_MODEL", "").strip()
        if not model:
            model = str(file_cfg.get("anthropic_model") or "").strip()

        base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip()
        if not base_url:
            base_url = str(file_cfg.get("anthropic_base_url") or "").strip()
        if not base_url:
            base_url = DEFAULT_ANTHROPIC_BASE_URL

        if not api_key:
            raise RuntimeError(
                "Missing Anthropic API key. Set ANTHROPIC_API_KEY or run: apex init"
            )
        if not model:
            raise RuntimeError(
                "Missing Anthropic model. Set ANTHROPIC_MODEL or run: apex init"
            )
        return AnthropicMessagesClient(
            AnthropicConfig(api_key=api_key, model=model, base_url=base_url)
        )

    raise RuntimeError(f"Unsupported LLM provider: {provider}")
