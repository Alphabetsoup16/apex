"""
MCP integration. Import ``create_mcp_server`` from ``apex.mcp.server`` (lazy here so
submodules like ``apex.mcp.input_guard`` load without the optional ``mcp`` dependency).
"""

from __future__ import annotations

from typing import Any

__all__ = ["create_mcp_server"]


def __getattr__(name: str) -> Any:
    if name == "create_mcp_server":
        from apex.mcp.server import create_mcp_server

        return create_mcp_server
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
