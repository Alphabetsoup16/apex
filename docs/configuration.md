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

## Conventions (optional)

- Repo-local: `.apex/conventions.md` (or `.apex/conventions.txt`)
- Global/company: set `APEX_GLOBAL_CONVENTIONS_PATH` to point at a file

APEX will merge global + repo-local + per-call `repo_conventions` (in that order).

## Findings policy (optional)

You can optionally suppress certain finding categories from the reported results.

- Repo-local: `.apex/policy.json`
- Global/company: set `APEX_GLOBAL_POLICY_PATH` to point at a JSON file

Schema (both locations):

```json
{
  "ignored_types": ["style", "formatting"],
  "ignored_severities": ["low"]
}
```

