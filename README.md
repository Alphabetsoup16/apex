# APEX (Adversarial Pipeline for Execution eXamination)

APEX is an MCP server that verifies LLM outputs using a layered pipeline:

- Ensemble generation (multi-path convergence)
- Adversarial review (structured findings)
- Optional executable ground truth for code (sandboxed backend; two independent pytest suites)

**Design focus:** APEX is tuned for the **light layer**—fast, diff-aware review amplification (ensemble + adversarial + inspection + optional small execution) so humans know *what to scrutinize*. Broader assurance—full test matrices, builds, SAST/DAST, dependency scanning, SonarQube, CodeQL, etc.—belongs in **CI** (e.g. GitHub Actions) on push/PR; APEX does not try to replace that pipeline.

## Verdicts

- `high_verified`: strong agreement + (when enabled) execution ground truth passed
- `needs_review`: inconclusive or execution not enabled
- `blocked`: extraction/validation failed, or safety/auditing blocked the run

## Quick Start

Install:

```bash
cd /path/to/apex
pip install -e .
```

Configure the LLM (Anthropic is the default provider). **Either** use the interactive wizard **or** set env vars (env wins if set):

```bash
apex init
```

**Or** with environment variables only:

```bash
export APEX_LLM_PROVIDER="anthropic"
export ANTHROPIC_API_KEY="..."
export ANTHROPIC_MODEL="claude-3-5-haiku-latest"
```

**Models:** APEX runs **many** LLM calls per run (ensemble paths, adversarial review, inspection, test generation). Prefer **smaller, faster** Anthropic tiers (**Haiku** or **Sonnet**); **Opus** is usually slower, pricier, and rarely needed for this workflow. See [Configuration → model choice](docs/configuration.md#choosing-an-anthropic-model).

See [Configuration](docs/configuration.md) for `~/.apex/config.json`, overrides, and why GitHub Copilot is not a direct option.

Optional: enable executable verification for code mode:

```bash
export APEX_EXECUTION_BACKEND_URL="http://localhost:8080/execute"
```

Execution backend details: see [Code execution backend contract](docs/code-execution.md).

Run APEX:

```bash
python3 -m apex serve --transport stdio
```

## Tool Interface

APEX exposes `apex.run` with:
- `prompt` (string)
- `mode` (`auto` | `text` | `code`) — `auto` uses a small keyword heuristic; prefer an explicit mode when classification must be reliable
- `code_ground_truth` (enables execution verification in `mode=code`)
- `ensemble_runs` (clamped server-side to **2–3**), `max_tokens`
- `known_good_baseline` (optional similarity downgrade for `high_verified`)

See:
- [Architecture](docs/architecture.md)
- [Flow chart](docs/flow.md)
- [Pipeline steps (extending verification)](docs/pipeline-steps.md)
- [Tool interface contract](docs/tool-interface.md)
- [Verification semantics](docs/verification.md)
- [Code execution backend contract](docs/code-execution.md)
- [Safety & auditing](docs/safety.md)
- [Configuration](docs/configuration.md)

## Limitations (Alpha)

- `high_verified` in code mode requires `code_ground_truth=true` and a configured execution backend.
- Doc-only inspection is best-effort; it does not replace running your real project test suite.

## Contributing

Use a virtualenv, install the package and dev tools, then run checks:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make check
```

`Makefile` uses `python -m ruff` when available; otherwise it looks for `vendor/bin/ruff` (local vendoring — not in git).

Regression-style checks for verdict + `pipeline_steps` order live under `tests/eval/` (deterministic mocks, no live LLM).

