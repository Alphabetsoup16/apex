from __future__ import annotations

from apex.config.env import env_str
from apex.llm.interface import LLMClient
from apex.llm.providers.anthropic_messages import AnthropicConfig, AnthropicMessagesClient
from apex.llm.user_config import DEFAULT_ANTHROPIC_BASE_URL, load_user_llm_config


def load_llm_client_from_env() -> LLMClient:
    """
    Load an ``LLMClient`` from the environment and/or user config file.

    Default ``llm_client_factory`` for ``ApexRunContext`` / ``apex_run`` when the caller
    does not inject one. Embedders may pass any ``() -> LLMClient`` instead.

    **Precedence (highest first):** environment variables, then ``~/.apex/config.json``
    (unless ``APEX_USER_CONFIG_PATH`` is set). This keeps CI and production on pure env
    while local devs can run ``apex init`` (or ``apex setup``).

    Default provider: ``anthropic`` (``APEX_LLM_PROVIDER``).
    """
    file_cfg = load_user_llm_config()

    provider = env_str("APEX_LLM_PROVIDER").lower()
    if not provider:
        provider = str(file_cfg.get("provider") or "anthropic").strip().lower() or "anthropic"

    if provider == "anthropic":
        api_key = env_str("ANTHROPIC_API_KEY")
        if not api_key:
            api_key = str(file_cfg.get("anthropic_api_key") or "").strip()

        model = env_str("ANTHROPIC_MODEL")
        if not model:
            model = str(file_cfg.get("anthropic_model") or "").strip()

        base_url = env_str("ANTHROPIC_BASE_URL")
        if not base_url:
            base_url = str(file_cfg.get("anthropic_base_url") or "").strip()
        if not base_url:
            base_url = DEFAULT_ANTHROPIC_BASE_URL

        if not api_key:
            raise RuntimeError("Missing Anthropic API key. Set ANTHROPIC_API_KEY or run: apex init")
        if not model:
            raise RuntimeError("Missing Anthropic model. Set ANTHROPIC_MODEL or run: apex init")
        return AnthropicMessagesClient(
            AnthropicConfig(api_key=api_key, model=model, base_url=base_url)
        )

    raise RuntimeError(f"Unsupported LLM provider: {provider}")
