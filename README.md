# APEX (Adversarial Pipeline for Execution eXamination)

## What we are trying to do

Large language models can sound confident even when they are wrong. APEX exists to give you a **second opinion** on an AI-generated answer—while you are still writing or reviewing—not to replace your full test and security pipeline.

In plain terms:

1. **You (or your agent)** send a prompt and a candidate answer to check.
2. **APEX** asks the model for several alternative answers and looks for agreement (**ensemble**).
3. **A separate review pass** hunts for problems and reports them as structured findings (**adversarial review**).
4. **If you use code mode**, it can optionally run tests against **your** execution backend so you see whether the code actually behaves as intended.

You get a **verdict** (`high_verified`, `needs_review`, or `blocked`) plus details you can use to decide what still needs human scrutiny. Think of it as **fast, review-time verification** for AI-assisted work—not a substitute for CI, SAST, dependency scanning, or your repo’s own test matrix. Use APEX when authoring or reviewing; keep your normal pipeline for shipping.

**How you use it:** APEX is an **MCP server**. Tools like Cursor or other MCP-aware hosts can call it (main tool: **`run`**) so verification fits into the same workflow where the model produced the answer.

---

**Mechanically,** the server checks LLM outputs with:

- **Ensemble** generation and convergence
- **Adversarial** review (structured findings)
- **Code mode:** optional execution against your backend (two independent pytest suites)

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
