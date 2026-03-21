# Configuration

Most behavior is controlled with **environment variables**. File-based LLM config is optional; see below.

## LLM (Anthropic)

Only Anthropic is implemented today.

### Wizard

```bash
apex init              # writes ~/.apex/config.json (key hidden)
apex init show         # file + env summary, no secrets printed
apex init clear        # delete config file
apex setup             # alias for apex init
```

**Copilot:** Not supported as a provider here—the MCP server runs outside the editor; use Anthropic or an HTTP API you control.

### Env vs file

If an env var is **non-empty**, it overrides `~/.apex/config.json` (or `APEX_USER_CONFIG_PATH`).

| Variable | Role |
|----------|------|
| `APEX_USER_CONFIG_PATH` | Alternate JSON path (tests, custom layout) |
| `APEX_LLM_PROVIDER` | Default `anthropic` |
| `ANTHROPIC_API_KEY` | Required for calls |
| `ANTHROPIC_MODEL` | Model id |
| `ANTHROPIC_BASE_URL` | Default `https://api.anthropic.com` |

### Picking a model

One APEX tool run triggers **many** calls (ensemble, reviews, tests in code mode). Cost and latency scale with per-call pricing.

| Tier | Use when |
|------|----------|
| **Haiku** | Default choice; usually enough for JSON-shaped outputs + reviews |
| **Sonnet** | Haiku quality is too weak for your task |
| **Opus** | Rarely worth it here—high cost/latency for this workload |

Confirm current model ids in [Anthropic’s docs](https://docs.anthropic.com/en/docs/about-claude/models).

### Config file

Written by `apex init`:

```json
{
  "version": 1,
  "provider": "anthropic",
  "anthropic_api_key": "...",
  "anthropic_model": "claude-3-5-haiku-latest",
  "anthropic_base_url": "https://api.anthropic.com"
}
```

On POSIX, saves use mode **600** where possible. Treat the file like a credential.

`apex serve` lazy-imports FastMCP; `apex init` does not.

### CLI streams

- Normal output → **stdout**
- Errors / fatal exits → **stderr**

## Code execution backend

| Variable | Purpose |
|----------|---------|
| `APEX_EXECUTION_BACKEND_URL` | Required for `code_ground_truth` execution |
| `APEX_EXECUTION_BACKEND_API_KEY` | Optional Bearer token |
| `APEX_EXECUTION_BACKEND_AUTH_HEADER` | Default `Authorization` |
| `APEX_EXECUTION_BACKEND_RETRIES` | Default `2` (502/503/504) |

## Top-level errors (sanitized by default)

If `apex_run` hits an **uncaught** exception before building a normal pipeline result, the tool still returns `verdict: blocked`. Clients get:

- **`error_code`** — Stable category (`apex.configuration`, `apex.validation`, `apex.network`, …)
- **`error`** — Short, safe message (no raw stack, paths, or URLs)
- **`error_type`** — Exception class name (diagnostic only)

| Variable | Effect |
|----------|--------|
| `APEX_EXPOSE_ERROR_DETAILS` | If truthy, adds **`error_detail`**: raw message truncated (~8k). **Avoid** on untrusted or multi-tenant MCP hosts. |

## Concurrency & run limits

`APEX_LLM_CONCURRENCY` (default `2`) caps concurrent **ensemble** LLM calls inside a single run.

**Whole-run** (process-wide) caps:

| Variable | Default | Effect |
|----------|---------|--------|
| `APEX_MAX_CONCURRENT_RUNS` | `0` (off) | Max concurrent `apex_run` invocations; extra calls → `verdict: blocked`, `error_code: apex.capacity` |
| `APEX_RUN_MAX_WALL_MS` | `0` (off) | Wall-clock timeout for the main pipeline body → `error_code: apex.run_timeout` |

Values are clamped (`RUN_LIMIT_*_CEILING` in `apex.config.constants`). See [robustness.md](robustness.md).

## Progress events (structured logs)

Coarse **run / pipeline / step** JSON lines on logger **`apex.progress`** (not LLM token streaming).

| Variable | Effect |
|----------|--------|
| `APEX_PROGRESS_LOG` | If truthy → emit `apex.progress/v1` events (see [progress-events.md](progress-events.md)) |

## Run ledger (SQLite)

Each finished `apex_run` can append one row + step rows to a local DB (WAL). Created on first write.

| Variable | Effect |
|----------|--------|
| — | Default file: **`~/.apex/ledger.sqlite3`** (logging **on**) |
| `APEX_LEDGER_DISABLED` | Truthy → no writes; `apex ledger` reports disabled |
| `APEX_LEDGER_PATH` | Override DB path |
| `APEX_LEDGER_STORE_STEP_DETAIL` | `0` (default): omit `pipeline_steps[*].detail` in DB. `1`: store JSON (truncated) |
| `APEX_LEDGER_MAX_DETAIL_CHARS` | Default `65536` |
| `APEX_LEDGER_BUSY_TIMEOUT_MS` | Default `2000` |

**CLI:** `apex ledger` / `apex ledger summary` — counts, verdict breakdown, trace-validation failures, recent runs.

**Inspect JSON:** `apex ledger query` (same shape as MCP `ledger_query`). Optional `--limit`, `--run-id`.

## Repo context (MCP read tools)

Optional allowlisted reads. [repo-context.md](repo-context.md).

| Variable | Effect |
|----------|--------|
| `APEX_REPO_CONTEXT_ROOT` | Directory path; unset → repo tools disabled |
| `APEX_REPO_CONTEXT_DISABLED` | Truthy → disabled |
| `APEX_REPO_CONTEXT_MAX_FILE_BYTES` | Per-file read cap |
| `APEX_REPO_CONTEXT_MAX_GLOB_RESULTS` | Max matches per glob |
| `APEX_REPO_CONTEXT_MAX_PATTERN_LEN` | Max pattern string length |

## Conventions merge

1. `APEX_GLOBAL_CONVENTIONS_PATH` (optional file)  
2. `.apex/conventions.md` or `.apex/conventions.txt` in repo  
3. Per-call `repo_conventions` on the tool  

Later steps override earlier.

## Findings policy

Loads `.apex/policy.json` (cwd) and/or `APEX_GLOBAL_POLICY_PATH`. Policy may drop **low** noise only; **`high` and `medium` are never removed** (verdicts cannot be weakened that way).

```json
{
  "ignored_types": ["style", "formatting"],
  "ignored_severities": ["low"]
}
```

## Tunable thresholds

See `apex.config.constants` (e.g. `HIGH_VERIFIED_CONVERGENCE_THRESHOLD`, ensemble clamp `ENSEMBLE_RUNS_*`).
