from __future__ import annotations

from apex.mcp.diagnostics import build_config_describe_snapshot, build_health_snapshot


def test_health_snapshot_schema() -> None:
    h = build_health_snapshot()
    assert h["schema"] == "apex.health/v1"
    assert "apex_version" in h
    assert "python_version" in h
    assert "ledger_enabled" in h
    assert "execution_backend_configured" in h
    assert "repo_context_enabled" in h


def test_config_describe_no_secrets() -> None:
    c = build_config_describe_snapshot()
    assert c["schema"] == "apex.config.describe/v1"
    blob = str(c)
    assert "sk-ant" not in blob.lower()
    assert "config_file" in c
    assert "environment" in c
