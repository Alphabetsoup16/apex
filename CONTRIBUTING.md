# Contributing

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make check
```

`make check` = Ruff on `src` and `tests`, then pytest. If `python -m ruff` is missing, use `vendor/bin/ruff` when present.

## Principles

- **MCP vs core:** `apex.pipeline.*` never imports FastMCP. Server wiring: `apex.mcp.server`.
- **One run:** Orchestration `run.py` → LLM body `run_execute.py` → frozen inputs `run_context.py`. [architecture.md](docs/architecture.md).
- **Monkeypatch the binding module** (e.g. `apex.pipeline.run_context.load_llm_client_from_env` for the default client factory; `apex.pipeline.run_execute` for `run_text_mode` / `run_code_mode`). [docs/README.md#where-tests-live](docs/README.md#where-tests-live).
- **Fakes:** [tests/fakes.py](tests/fakes.py) — `FakeLLMClient`, `sample_code_solution`, `sample_code_tests`.

## Style

Ruff (line length 100, Python 3.10+). Prefer explicit types on public APIs; `LLMClient` is a structural protocol.

## Docs

- **Index:** [docs/README.md](docs/README.md)
- **Schema / contract tokens:** `apex.config.contracts` — [contracts.py](src/apex/config/contracts.py) · [compatibility.md](docs/compatibility.md)
- **After behavior changes:** update the relevant doc; for MCP I/O, [tool-interface.md](docs/tool-interface.md) / [mcp-tools.md](docs/mcp-tools.md)

## Eval regressions

[tests/eval/](tests/eval/) — verdict + ordered `pipeline_steps`; cases in [tests/eval/cases.py](tests/eval/cases.py).

## Agents

Quick links: [AGENTS.md](AGENTS.md).
