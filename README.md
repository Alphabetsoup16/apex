# APEX (Adversarial Pipeline for Execution eXamination)

## What we are trying to do

Models can be wrong and still sound confident. APEX is a **quick second check** on an AI draft while you write or review—not a substitute for CI, security scans, or your repo’s full tests.

Run it as an **MCP server**; hosts call **`run`** with a prompt and the answer to verify. APEX generates several alternatives and compares them (**ensemble**), runs an **adversarial review** with clear structured findings, and in **code mode** can execute tests on **your** backend. You get a verdict (`high_verified`, `needs_review`, or `blocked`) and signals that tell you where a human should still look.

Under the hood: ensemble convergence, adversarial review, and optional backend execution (two independent pytest suites).

## Verdicts

| Verdict | Meaning (short) |
|---------|------------------|
| `high_verified` | Strong convergence + no blocking findings + (code) execution passed when ground truth is on |
| `needs_review` | Inconclusive, or execution off/unknown, or baseline downgrade |
| `blocked` | Validation/safety/execution failure, or top-level run error |

## Quick Start

```bash
cd /path/to/apex
pip install -e .
```

**LLM:** Interactive setup or env-only (non-empty env wins over file):

```bash
apex init
# or
export APEX_LLM_PROVIDER="anthropic"
export ANTHROPIC_API_KEY="..."
export ANTHROPIC_MODEL="claude-3-5-haiku-latest"
```

APEX issues **many** LLM calls per tool run—prefer **Haiku** or **Sonnet** over **Opus** for cost/latency unless you deliberately need more capability. [Model notes](docs/configuration.md#picking-a-model).

**Config file & Copilot:** [Configuration](docs/configuration.md) (`~/.apex/config.json`, overrides; Copilot is not a supported provider for this process).

**Run ledger:** Each `apex_run` is logged to `~/.apex/ledger.sqlite3` by default. `apex ledger summary` to inspect; `APEX_LEDGER_DISABLED=1` to turn off. [Run ledger](docs/configuration.md#run-ledger-sqlite).

**Progress events (optional):** Set `APEX_PROGRESS_LOG=1` for structured JSON lines on logger `apex.progress` (run/pipeline/step boundaries—not LLM token streaming). [progress-events](docs/progress-events.md).

**Code execution (optional):**

```bash
export APEX_EXECUTION_BACKEND_URL="http://localhost:8080/execute"
```

[Backend contract](docs/code-execution.md).

**Start server:**

```bash
python3 -m apex serve --transport stdio
```

## MCP tools

Primary: **`run`** (verification). Operator helpers: **`health`**, **`describe_config`**, **`ledger_query`**, **`cancel_run`**, optional **`repo_*`** (allowlisted FS read/glob via `APEX_REPO_CONTEXT_ROOT`). See [mcp-tools.md](docs/mcp-tools.md) · [repo-context.md](docs/repo-context.md).

Main `run` inputs: `prompt`, `mode` (`auto` | `text` | `code`), `code_ground_truth`, `ensemble_runs` (clamped **2–3**), `max_tokens`, optional `known_good_baseline`, optional `supplementary_context` (code inspection only).

**Docs:**

- [Architecture](docs/architecture.md) · [Flow](docs/flow.md) · [Pipeline steps](docs/pipeline-steps.md)
- [Integrations](docs/integration.md) · [Skill playbook](docs/skill-apex-verification.md) (agent hosts)
- [MCP tools](docs/mcp-tools.md) · [Tool contract](docs/tool-interface.md) · [Verification](docs/verification.md)
- [Code execution](docs/code-execution.md) · [Safety](docs/safety.md) · [Configuration](docs/configuration.md) · [Compatibility](docs/compatibility.md)

## Limitations (alpha)

- `high_verified` in code mode needs `code_ground_truth=true` and a working backend.
- Doc-only inspection does not replace your repo’s real test suite.

## Contributing

**[CONTRIBUTING.md](CONTRIBUTING.md)** · **[AGENTS.md](AGENTS.md)**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make check
```

Ruff: `python -m ruff` or `vendor/bin/ruff`. Regressions: `tests/eval/`.
