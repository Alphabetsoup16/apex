# API compatibility

What integrators can rely on when consuming JSON from APEX, and how version tokens are managed in code.

**Module:** `apex.config.contracts` (import constants—do not copy string literals into call sites).

## Schema and contract tokens

| Literal value | Python constant | Where it appears |
|---------------|-----------------|------------------|
| `apex.health/v1` | `HEALTH_SCHEMA_V1` | MCP **`health`**.`schema` |
| `apex.verify_step.v1` | `VERIFICATION_CONTRACT_V1` | MCP **`health`**.`verification_contract` |
| `apex.config.describe/v1` | `CONFIG_DESCRIBE_SCHEMA_V1` | MCP **`describe_config`**.`schema` |
| `apex.telemetry/v1` | `TELEMETRY_SCHEMA_V1` | `metadata.telemetry.schema` after `finalize_run_result` |
| `apex.uncertainty/v1` | `UNCERTAINTY_SCHEMA_V1` | `metadata.uncertainty.schema` after `finalize_run_result` |

## Change policy (practical)

| Change type | Expectation |
|-------------|----------------|
| **Additive** | New optional `metadata` keys, new `health` keys, new pipeline step ids documented in [pipeline-steps.md](pipeline-steps.md) — clients should ignore unknown fields. |
| **Breaking** | Removing or repurposing fields, changing `verdict` rules without documentation, renaming step ids that clients rely on — bump the relevant **`…_V1` → `…_V2`**, update this doc and [tool-interface.md](tool-interface.md) / [mcp-tools.md](mcp-tools.md). |

## Pipeline invariants

See [robustness.md](robustness.md) (finalize, trace validation, ledger, verdict semantics).

---

[Index of all docs](README.md)
