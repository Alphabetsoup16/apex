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
- `APEX_EXECUTION_BACKEND_RETRIES` (optional; default `2`) — retries transient 502/503/504 responses

## Concurrency

- `APEX_LLM_CONCURRENCY` (default: `2`)

This bounds concurrent ensemble generation and helps keep latency predictable.

## Conventions (optional)

- Repo-local: `.apex/conventions.md` (or `.apex/conventions.txt`)
- Global/company: set `APEX_GLOBAL_CONVENTIONS_PATH` to point at a file

APEX will merge global + repo-local + per-call `repo_conventions` (in that order).

## Findings policy (optional)

Loaded by `apex.config.policy` from the paths below. Policy can **only filter findings that are not verdict-critical**: **`high` and `medium` severities are always kept** so blocks and `high_verified` gating cannot be weakened. Typically you use this to hide noisy **`low`** findings by type or severity.

- Repo-local: `.apex/policy.json` (resolved from the process current working directory unless you pass `repo_root` to `load_findings_policy` in custom integrations)
- Global/company: set `APEX_GLOBAL_POLICY_PATH` to point at a JSON file

Schema (both locations):

```json
{
  "ignored_types": ["style", "formatting"],
  "ignored_severities": ["low"]
}
```

## Scoring thresholds (code reference)

Tune in `apex.config.constants` (documented in that module), including:

- `HIGH_VERIFIED_CONVERGENCE_THRESHOLD` — minimum ensemble convergence for `high_verified` when other signals allow it
- `TEXT_ANSWER_CONVERGENCE_WEIGHT` / `TEXT_CLAIMS_CONVERGENCE_WEIGHT` — text convergence / best-candidate selection blend
- `ENSEMBLE_RUNS_MIN_EFFECTIVE` / `ENSEMBLE_RUNS_MAX_EFFECTIVE` — clamp applied in `apex_run`

