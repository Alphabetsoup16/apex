# Agent & contributor map

| Topic | Doc |
|-------|-----|
| Workflow, tests, fakes | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Schema tokens / API evolution | [docs/compatibility.md](docs/compatibility.md) · `apex.config.contracts` |
| Package layout | [docs/architecture.md](docs/architecture.md) |
| MCP `run` + metadata | [docs/mcp-tools.md](docs/mcp-tools.md), [docs/tool-interface.md](docs/tool-interface.md) |
| Test file roles | [docs/README.md#where-tests-live](docs/README.md#where-tests-live) |
| Hosts / Python embed | [docs/integration.md](docs/integration.md) |
| Pipeline stages | [docs/pipeline-steps.md](docs/pipeline-steps.md), [docs/flow.md](docs/flow.md) |

**Import:** `from apex.pipeline import apex_run, LLMClientFactory, resolve_run_modes` (`apex/pipeline/__init__.py`).

**Gate:** `make check` (Ruff + pytest).
