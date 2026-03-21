from __future__ import annotations

import pytest

mcp = pytest.importorskip("mcp")


def test_create_mcp_server_registers_expected_tools() -> None:
    """Fails in full installs if tools are renamed/removed without updating tests."""
    from apex.mcp.server import create_mcp_server

    server = create_mcp_server()
    mgr = getattr(server, "_tool_manager", None)
    assert mgr is not None, "FastMCP internal API changed (_tool_manager missing)"
    tools = getattr(mgr, "_tools", None)
    assert isinstance(tools, dict) and tools, "No tools registered on FastMCP server"
    names = {t.name for t in tools.values()}
    expected = {
        "run",
        "health",
        "describe_config",
        "ledger_query",
        "cancel_run",
        "repo_context_status",
        "repo_read_file",
        "repo_glob",
    }
    missing = expected - names
    assert not missing, f"MCP tools missing from server: {sorted(missing)}; have {sorted(names)}"
