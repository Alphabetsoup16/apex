# APEX (Adversarial Pipeline for Execution eXamination)

APEX is an MCP server that verifies LLM outputs using:
1) multi-path generation (ensemble),
2) an adversarial review pass (structured findings),
3) optional code execution as ground truth via a sandboxed backend.

Verdicts:
- `high_verified`
- `needs_review`
- `blocked`

## Requirements

- Python `>= 3.10`
- LLM provider (currently Anthropic-only):
  - `APEX_LLM_PROVIDER` (default: `anthropic`)
  - `ANTHROPIC_API_KEY`
  - `ANTHROPIC_MODEL`
  - optional `ANTHROPIC_BASE_URL` (default: `https://api.anthropic.com`)
- (For code mode) an execution backend endpoint reachable from the APEX process

## Execution latency expectation
With `APEX_EXECUTION_BACKEND_URL` pointing at a live backend, per-run latency is mostly LLM time plus a single `pytest` job on the backend.

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
- `ensemble_runs` (default `3`)
- `max_tokens` (default `1024`)

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

## Verdict semantics for code mode

- With `code_ground_truth=true`, APEX generates and executes two independent pytest suites, and may return `high_verified` only if the sandboxed execution backend reports `pass=true` for both.
- With `code_ground_truth=false`, APEX will never return `high_verified` for code; it will return `needs_review` (with `metadata.verification_scale = "spec_only"`).

When APEX calls the backend, it also includes conservative capability flags in `limits`:
- `allow_network` (default `false`)
- `allow_filesystem_write` (default `false`)
- `allow_dependency_install` (default `false`)

## Security notes

- Code “ground truth” only works if your execution backend is properly sandboxed (no network by default, least-privilege filesystem, strict CPU/memory/time limits).
- APEX also redacts common secret patterns from prompts and logs before sending to the LLM/reviewers.

