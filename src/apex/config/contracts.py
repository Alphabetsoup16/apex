"""
Versioned string identifiers for JSON payloads (MCP diagnostics and tool ``metadata``).

Import these constants in application code and tests—do not duplicate literals.
When bumping a version (e.g. ``…_V1`` → ``…_V2``), update ``docs/compatibility.md``
and dependent docs (``mcp-tools``, ``tool-interface``).
"""

from __future__ import annotations

HEALTH_SCHEMA_V1 = "apex.health/v1"
CONFIG_DESCRIBE_SCHEMA_V1 = "apex.config.describe/v1"
VERIFICATION_CONTRACT_V1 = "apex.verify_step.v1"
TELEMETRY_SCHEMA_V1 = "apex.telemetry/v1"
UNCERTAINTY_SCHEMA_V1 = "apex.uncertainty/v1"

__all__ = [
    "CONFIG_DESCRIBE_SCHEMA_V1",
    "HEALTH_SCHEMA_V1",
    "TELEMETRY_SCHEMA_V1",
    "UNCERTAINTY_SCHEMA_V1",
    "VERIFICATION_CONTRACT_V1",
]
