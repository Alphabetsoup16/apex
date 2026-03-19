# APEX (Adversarial Pipeline for Execution eXamination)

APEX is an MCP server that verifies LLM outputs using a layered approach:

- Multi-path generation (ensemble voting)
- An adversarial review pass (structured findings)
- Optional executable ground truth for code via a sandboxed backend

## Verdicts

- `high_verified`: executable ground truth enabled (code mode) and both suites pass
- `needs_review`: verification was inconclusive
- `blocked`: extraction/validation failed, adversarial findings are too severe, or executable checks failed

## Requirements

- Python `>= 3.10`

## Configuration

- LLM provider (currently Anthropic-only):
  - `APEX_LLM_PROVIDER` (default: `anthropic`)
  - `ANTHROPIC_API_KEY`
  - `ANTHROPIC_MODEL`
  - optional `ANTHROPIC_BASE_URL` (default: `https://api.anthropic.com`)
- (For code mode) executable backend endpoint reachable from the APEX process:
  - `APEX_EXECUTION_BACKEND_URL` (optional unless `code_ground_truth=true`)
- Optional backend authorization:
  - `APEX_EXECUTION_BACKEND_API_KEY` (enables Bearer auth)
  - `APEX_EXECUTION_BACKEND_AUTH_HEADER` (optional; default `Authorization`)
- Optional bounded concurrency:
  - `APEX_LLM_CONCURRENCY` (default: `2`)

## Execution latency expectation
With `APEX_EXECUTION_BACKEND_URL` pointing at a live backend, per-run latency is mostly LLM time plus backend execution. In code mode with `code_ground_truth=true`, APEX runs two independent pytest suites (`tests_v1` and `tests_v2`).

## Setup

Clone and install:

```bash
cd /path/to/apex
pip install -e .
```

Set environment variables:

```bash
export APEX_LLM_PROVIDER="anthropic"
export ANTHROPIC_API_KEY="..."
export ANTHROPIC_MODEL="claude-3-5-sonnet-latest"

# Optional: required only if you enable executable verification for code
export APEX_EXECUTION_BACKEND_URL="http://localhost:8080/execute"
```

## Run APEX as an MCP stdio server

```bash
python3 -m apex serve --transport stdio
```

This MCP server exposes one tool named `run`.

## Connect in Claude Code (MCP -> local stdio)

From inside a shell:

```bash
claude mcp add --transport stdio apex -- python3 -m apex serve --transport stdio
```

If you prefer to pass secrets via environment (recommended for local stdio):

```bash
claude mcp add --transport stdio --env ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" apex -- python3 -m apex serve --transport stdio
```

## Connect in Cursor IDE (project `.cursor/mcp.json`)

Create a file at `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "apex": {
      "command": "python3",
      "args": ["-m", "apex", "serve", "--transport", "stdio"],
      "env": {
        "APEX_LLM_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "${env:ANTHROPIC_API_KEY}",
        "ANTHROPIC_MODEL": "${env:ANTHROPIC_MODEL}"
      }
    }
  }
}
```

Restart Cursor after adding/updating this file.

## Tool input (what the user actually provides)

Tool parameters:
- `prompt` (string)
- `mode` (default `auto`; `auto` infers `text` vs `code`)
- `code_ground_truth` (default `false`; only affects `mode=code`)
- `known_good_baseline` (optional string)
- `ensemble_runs` (default `3`)
- `max_tokens` (default `1024`)

### Output fields

The tool returns JSON with:

- `verdict` (`high_verified` | `needs_review` | `blocked`)
- `output` (string; best candidate output)
- `metadata` (structured run metadata)
- `adversarial_review` (structured findings, or `null`)
- `execution` (execution result for code mode, or `null`)

Notes on `metadata`:

- if `known_good_baseline` is provided, `metadata.baseline_similarity` may be included
- if chain-of-thought leakage is detected, `metadata.cot_audit` is included and the verdict is `blocked`

## Code-mode execution contract (what the backend must implement)

APEX will `POST` JSON to `{APEX_EXECUTION_BACKEND_URL}/execute` (if the URL already ends with `/execute`, it is used as-is).

Optional auth:
- If `APEX_EXECUTION_BACKEND_API_KEY` is set, APEX sends `Authorization: Bearer <key>`
- Use `APEX_EXECUTION_BACKEND_AUTH_HEADER` to override the header name (default `Authorization`)

### Request shape

APEX sends:

```json
{
  "language": "python",
  "run_id": "string",
  "files": [{ "path": "solution.py", "content": "..." }],
  "tests": [{ "path": "test_solution.py", "content": "..." }],
  "limits": {
    "cpu_seconds": 20,
    "memory_mb": 512,
    "wall_time_seconds": 60,
    "allow_network": false,
    "allow_filesystem_write": false,
    "allow_dependency_install": false
  }
}
```

Your backend should return JSON shaped like:

```json
{
  "pass": true,
  "stdout": "...",
  "stderr": "...",
  "duration_ms": 1234
}
```

The required fields above must be present. Optional fields may be included.

## Verdict Semantics for Code Mode

- With `code_ground_truth=true`:
  - APEX executes two independent pytest suites (`tests_v1` and `tests_v2`)
  - `high_verified` is only possible if the backend reports `pass=true` for both suites
- With `code_ground_truth=false`:
  - APEX will never return `high_verified` for code
  - it downgrades to `needs_review` with `metadata.verification_scale = "spec_only"`

When APEX calls the backend, it also includes conservative capability flags in `limits`:
- `allow_network` (default `false`)
- `allow_filesystem_write` (default `false`)
- `allow_dependency_install` (default `false`)

## Chain-of-Thought Auditing

APEX blocks runs when it detects common chain-of-thought leakage markers in either:

- text mode (`answer` and `key_claims`)
- code mode (generated solution code content)

## Security Notes

- Executable ground truth is meaningful only if your backend is properly sandboxed (no network by default, least-privilege filesystem, strict CPU/memory/time limits).
- APEX also redacts common secret patterns from prompts before sending to the LLM and reviewers.

