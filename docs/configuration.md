# Configuration

APEX uses environment variables for configuration.

## LLM Provider

Currently, only Anthropic is implemented.

### Local wizard (easiest for dev machines)

After `pip install -e .`:

```bash
apex init              # interactive: API key (hidden), model, base URL → ~/.apex/config.json
apex init show         # file + env summary (no secrets)
apex init clear        # remove ~/.apex/config.json
apex setup             # same as `apex init` (alias)
```

- **GitHub Copilot** is **not** a selectable provider: it is tied to your editor session and does not expose a supported API for a separate MCP server process. Use Anthropic (or set env vars to hit an OpenAI-compatible proxy you control).

### Environment variables (override file when set)

Highest precedence: if a variable is **non-empty**, it wins over `~/.apex/config.json`.

- `APEX_USER_CONFIG_PATH` — optional path to the JSON file instead of `~/.apex/config.json` (tests, advanced layouts)
- `APEX_LLM_PROVIDER` (default: `anthropic`)
- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MODEL`
- `ANTHROPIC_BASE_URL` (optional; default: `https://api.anthropic.com`)

### Choosing an Anthropic model

APEX is **call-heavy**: multiple ensemble generations, adversarial review, doc inspection (code), optional test suites, etc. Cost and latency scale with **per-call** pricing and parallelism.

| Tier | When to use |
|------|----------------|
| **Haiku** (e.g. `claude-3-5-haiku-latest` or current Haiku id from [Anthropic docs](https://docs.anthropic.com/en/docs/about-claude/models)) | **Default recommendation** for everyday use: lower cost and latency; often enough for structured JSON + review passes. |
| **Sonnet** (e.g. `claude-3-5-sonnet-latest` or current Sonnet id) | If **generated code or answers** look weak with Haiku, step up here for better reasoning on the same pipeline. |
| **Opus** | **Usually avoid** for APEX: highest cost/latency; reserve for rare cases where you explicitly need maximum capability and accept the bill. |

Exact model strings change over time—always confirm the id in Anthropic’s model documentation.

### Config file shape (`~/.apex/config.json`)

Written by `apex init` / `apex setup`:

```json
{
  "version": 1,
  "provider": "anthropic",
  "anthropic_api_key": "...",
  "anthropic_model": "claude-3-5-haiku-latest",
  "anthropic_base_url": "https://api.anthropic.com"
}
```

On POSIX the config file is chmod **`600`** when possible, and the short-lived `config.json.tmp` used during saves is restricted the same way before rename. **Treat `~/.apex/config.json` like a password file** (plaintext secret).

`apex serve` loads MCP/FastMCP only for that subcommand; `apex init` / `apex setup` do not import the MCP stack.

### CLI output (scripting)

- Normal prompts and summaries go to **stdout**.
- Errors and fatal messages (e.g. missing API key after `apex llm`) go to **stderr** with a non-zero exit code where applicable.

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

