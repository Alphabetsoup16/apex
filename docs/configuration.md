# Configuration

APEX uses environment variables for configuration.

## LLM Provider

Currently, only Anthropic is implemented.

- `APEX_LLM_PROVIDER` (default: `anthropic`)
- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MODEL`
- `ANTHROPIC_BASE_URL` (optional; default: `https://api.anthropic.com`)

## Code Execution Backend (optional)

- `APEX_EXECUTION_BACKEND_URL` (optional; required only for `code_ground_truth=true`)
- `APEX_EXECUTION_BACKEND_API_KEY` (optional; enables Bearer auth)
- `APEX_EXECUTION_BACKEND_AUTH_HEADER` (optional; default `Authorization`)

## Concurrency

- `APEX_LLM_CONCURRENCY` (default: `2`)

This bounds concurrent ensemble generation and helps keep latency predictable.

