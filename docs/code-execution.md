# Code Execution Backend Contract

When `mode=code` and `code_ground_truth=true`, APEX:
- Generates a `solution.py`
- Generates two independent pytest suites (`tests_v1` and `tests_v2`)
- Calls your execution backend for each suite

When `code_ground_truth=true`, `high_verified` additionally requires both suites to report `pass=true` (along with convergence and adversarial gates — see [verification.md](verification.md)).

If `APEX_EXECUTION_BACKEND_URL` is unset or the backend errors, execution may be treated as inconclusive (`needs_review` / pass unknown) per pipeline logic.

## Endpoint

APEX will `POST` JSON to:

`{APEX_EXECUTION_BACKEND_URL}/execute`

If `APEX_EXECUTION_BACKEND_URL` already ends with `/execute`, it is used as-is.

## Optional authorization

- If `APEX_EXECUTION_BACKEND_API_KEY` is set, APEX sends:
  - `Authorization: Bearer <key>` (default)
- Use `APEX_EXECUTION_BACKEND_AUTH_HEADER` to override the header name.

## Request shape

APEX sends:

```json
{
  "language": "python",
  "run_id": "unique-run-id",
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

## Response shape

Your backend should return JSON shaped like:

```json
{
  "pass": true,
  "stdout": "...",
  "stderr": "...",
  "duration_ms": 1234
}
```

`pass`, `stdout`, `stderr`, and `duration_ms` are required.

The client may accept **additional** optional fields on the response (e.g. `exit_code`, `timed_out`, `resource_stats`, `logs`) for observability; APEX maps the core fields into `ExecutionResult`.

## Retries

- `APEX_EXECUTION_BACKEND_RETRIES` (default `2`): retries on transient HTTP **502 / 503 / 504** responses with exponential backoff.

