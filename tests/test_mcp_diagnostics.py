from __future__ import annotations

from apex.config.contracts import (
    CONFIG_DESCRIBE_SCHEMA_V1,
    HEALTH_SCHEMA_V1,
    VERIFICATION_CONTRACT_V1,
)
from apex.mcp.diagnostics import build_config_describe_snapshot, build_health_snapshot


def test_health_snapshot_schema(monkeypatch) -> None:
    monkeypatch.delenv("APEX_MAX_CONCURRENT_RUNS", raising=False)
    monkeypatch.delenv("APEX_RUN_MAX_WALL_MS", raising=False)
    h = build_health_snapshot()
    assert h["schema"] == HEALTH_SCHEMA_V1
    assert h["verification_contract"] == VERIFICATION_CONTRACT_V1
    assert "apex_version" in h
    assert "python_version" in h
    assert "ledger_enabled" in h
    assert "execution_backend_configured" in h
    assert "repo_context_enabled" in h
    assert h["run_limits"] == {"max_concurrent": 0, "wall_ms": 0}


def test_config_describe_no_secrets() -> None:
    c = build_config_describe_snapshot()
    assert c["schema"] == CONFIG_DESCRIBE_SCHEMA_V1
    blob = str(c)
    assert "sk-ant" not in blob.lower()
    assert "config_file" in c
    assert "environment" in c
