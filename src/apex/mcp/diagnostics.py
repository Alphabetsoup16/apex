"""
Non-secret operator snapshots for MCP tools (``health``, ``describe_config``).

Schemas are versioned strings so clients can evolve without breaking parsers.
"""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version

from apex.config.contracts import (
    CONFIG_DESCRIBE_SCHEMA_V1,
    HEALTH_SCHEMA_V1,
    VERIFICATION_CONTRACT_V1,
)
from apex.config.env import env_str, env_str_or_none
from apex.ledger import load_ledger_config, resolve_ledger_db_path
from apex.llm.user_config import load_user_llm_config, user_config_path
from apex.observability.progress_events import progress_log_enabled
from apex.repo_context.config import load_repo_context_config
from apex.runtime.run_limits import load_run_limit_settings


def _package_version() -> str:
    try:
        return version("apex")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def build_health_snapshot() -> dict[str, object]:
    """
    Safe process / config **flags** only (no API keys, no raw paths beyond config file hint).

    The returned ``schema`` value is ``HEALTH_SCHEMA_V1`` from ``apex.config.contracts``.
    """
    ledger_path = resolve_ledger_db_path()
    ledger_cfg = load_ledger_config()
    exec_url = env_str("APEX_EXECUTION_BACKEND_URL")
    lim = load_run_limit_settings()
    return {
        "schema": HEALTH_SCHEMA_V1,
        # Stable hint for stateful orchestrators: one ``run`` = one verification outcome.
        "verification_contract": VERIFICATION_CONTRACT_V1,
        "apex_version": _package_version(),
        "python_version": sys.version.split()[0],
        "llm_provider_default": env_str("APEX_LLM_PROVIDER") or "anthropic",
        "ledger_enabled": ledger_cfg is not None,
        "ledger_path_configured": ledger_path is not None,
        "execution_backend_configured": bool(exec_url),
        "progress_log_enabled": progress_log_enabled(),
        "repo_context_enabled": load_repo_context_config() is not None,
        "run_limits": {"max_concurrent": lim.max_concurrent, "wall_ms": lim.wall_ms},
    }


def build_config_describe_snapshot() -> dict[str, object]:
    """
    Effective LLM configuration **shape** (file + env), never secret values.

    The returned ``schema`` value is ``CONFIG_DESCRIBE_SCHEMA_V1`` from ``apex.config.contracts``.
    """
    path = user_config_path()
    fc = load_user_llm_config()
    file_block: dict[str, object] = {
        "path": str(path),
        "exists": path.is_file(),
    }
    if fc:
        prov = str(fc.get("provider", "") or "")
        file_block["provider"] = prov
        if prov == "anthropic":
            file_block["anthropic_model"] = str(fc.get("anthropic_model", "") or "")
            file_block["anthropic_base_url"] = str(fc.get("anthropic_base_url", "") or "")
            key = (fc.get("anthropic_api_key") or "").strip()
            file_block["anthropic_api_key"] = "set" if key else "empty"
        elif prov == "openai":
            file_block["openai_model"] = str(fc.get("openai_model", "") or "")
            ok = (fc.get("openai_api_key") or "").strip()
            file_block["openai_api_key"] = "set" if ok else "empty"
        elif prov == "bedrock":
            file_block["bedrock_model_id"] = str(fc.get("bedrock_model_id", "") or "")
    else:
        file_block["provider"] = None

    ak = env_str("ANTHROPIC_API_KEY")
    ok = env_str("OPENAI_API_KEY")
    return {
        "schema": CONFIG_DESCRIBE_SCHEMA_V1,
        "config_file": file_block,
        "environment": {
            "APEX_LLM_PROVIDER": env_str_or_none("APEX_LLM_PROVIDER"),
            "APEX_USER_CONFIG_PATH": env_str_or_none("APEX_USER_CONFIG_PATH"),
            "ANTHROPIC_API_KEY": "set" if ak else None,
            "ANTHROPIC_MODEL": env_str_or_none("ANTHROPIC_MODEL"),
            "ANTHROPIC_BASE_URL": env_str_or_none("ANTHROPIC_BASE_URL"),
            "OPENAI_API_KEY": "set" if ok else None,
            "OPENAI_MODEL": env_str_or_none("OPENAI_MODEL"),
            "OPENAI_BASE_URL": env_str_or_none("OPENAI_BASE_URL"),
            "BEDROCK_MODEL_ID": env_str_or_none("BEDROCK_MODEL_ID"),
            "AWS_REGION": env_str_or_none("AWS_REGION"),
            "BEDROCK_REGION": env_str_or_none("BEDROCK_REGION"),
        },
    }
