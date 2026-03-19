# APEX (Adversarial Pipeline for Execution eXamination)

APEX is an MCP server that verifies LLM outputs using a layered pipeline:

- Ensemble generation (multi-path convergence)
- Adversarial review (structured findings)
- Optional executable ground truth for code (sandboxed backend; two independent pytest suites)

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

Configure Anthropic (default provider):

```bash
export APEX_LLM_PROVIDER="anthropic"
export ANTHROPIC_API_KEY="..."
export ANTHROPIC_MODEL="claude-3-5-sonnet-latest"
```

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
- `mode` (`auto` | `text` | `code`)
- `code_ground_truth` (enables execution verification in `mode=code`)
- `ensemble_runs`, `max_tokens`
- `known_good_baseline` (optional similarity downgrade for `high_verified`)

See:
- [Tool interface contract](docs/tool-interface.md)
- [Verification semantics](docs/verification.md)
- [Code execution backend contract](docs/code-execution.md)
- [Safety & auditing](docs/safety.md)
- [Configuration](docs/configuration.md)

## Limitations (Alpha)

- `high_verified` in code mode requires `code_ground_truth=true` and a configured execution backend.
- Doc-only inspection is best-effort; it does not replace running your real project test suite.

## Contributing

Run tests:

```bash
PYTHONPATH=src:vendor pytest
```

Report issues and propose improvements via GitHub PRs.

