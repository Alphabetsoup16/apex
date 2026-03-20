from __future__ import annotations

import json
from pathlib import Path

import pytest

from apex.llm import loader as llm_loader
from apex.llm.user_config import load_user_llm_config, save_user_llm_config, user_config_path


def test_load_llm_client_uses_file_when_env_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg_path = tmp_path / "cfg.json"
    monkeypatch.setenv("APEX_USER_CONFIG_PATH", str(cfg_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("APEX_LLM_PROVIDER", raising=False)

    save_user_llm_config(
        {
            "provider": "anthropic",
            "anthropic_api_key": "sk-test-key",
            "anthropic_model": "claude-test",
            "anthropic_base_url": "https://api.anthropic.com",
        }
    )

    client = llm_loader.load_llm_client_from_env()
    assert client.model == "claude-test"


def test_env_overrides_user_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg_path = tmp_path / "cfg.json"
    monkeypatch.setenv("APEX_USER_CONFIG_PATH", str(cfg_path))
    save_user_llm_config(
        {
            "provider": "anthropic",
            "anthropic_api_key": "from-file",
            "anthropic_model": "from-file-model",
            "anthropic_base_url": "https://api.anthropic.com",
        }
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    monkeypatch.setenv("ANTHROPIC_MODEL", "from-env-model")

    client = llm_loader.load_llm_client_from_env()
    assert client.model == "from-env-model"


def test_missing_key_error_suggests_setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg_path = tmp_path / "empty.json"
    cfg_path.write_text(json.dumps({"version": 1, "provider": "anthropic"}), encoding="utf-8")
    monkeypatch.setenv("APEX_USER_CONFIG_PATH", str(cfg_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    with pytest.raises(RuntimeError, match="apex init"):
        llm_loader.load_llm_client_from_env()


def test_user_config_path_respects_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    monkeypatch.setenv("APEX_USER_CONFIG_PATH", str(p))
    assert user_config_path() == p


def test_load_user_llm_config_empty_for_bad_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("APEX_USER_CONFIG_PATH", str(p))
    assert load_user_llm_config() == {}
