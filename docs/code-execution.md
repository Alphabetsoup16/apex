# Code Execution Backend Contract

When `mode=code` and `code_ground_truth=true`, APEX:
- Generates a `solution.py`
- Generates two independent pytest suites (`tests_v1` and `tests_v2`)
- Calls your execution backend for each suite

`high_verified` in code mode is only possible when the backend reports `pass=true` for both suites.

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

