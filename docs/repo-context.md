# Repo context (explicit filesystem reads)

Opt-in, **allowlisted** read-only access so clients can pull snippets into `run` (e.g. `supplementary_context` or `repo_conventions`) without RAG or background indexing.

## Enable

| Variable | Effect |
|----------|--------|
| `APEX_REPO_CONTEXT_ROOT` | Absolute or `~` path to the **single** allowed repository root (required to enable tools) |
| `APEX_REPO_CONTEXT_DISABLED` | If truthy → tools off even if `ROOT` is set |
| `APEX_REPO_CONTEXT_MAX_FILE_BYTES` | Cap per `repo_read_file` (default from `REPO_CONTEXT_DEFAULT_MAX_FILE_BYTES`; hard ceiling in constants) |
| `APEX_REPO_CONTEXT_MAX_GLOB_RESULTS` | Max file rows per `repo_glob` |
| `APEX_REPO_CONTEXT_MAX_PATTERN_LEN` | Max glob pattern string length |

## MCP tools

| Tool | Role |
|------|------|
| `repo_context_status` | `apex.repo_context/v1` — enabled flag, resolved root, limits, `root_exists` |
| `repo_read_file` | `apex.repo_context.read/v1` — UTF-8 text, `errors=replace`, `truncated` if over byte cap |
| `repo_glob` | `apex.repo_context.glob/v1` — pathlib `glob` from root; `truncated` if more than max matches |

Paths and patterns must be **root-relative** (no leading `/`, no `..` segments, no absolute paths).

## Security notes

- **No silent crawl** — only explicit `glob` or `read` calls.
- **Symlink escape** — resolved paths must stay under the resolved root.
- **Binary / secrets** — still operator responsibility; this layer does not redact file contents.

## Non-goals

- Vector search / embeddings / incremental index (see [robustness.md](robustness.md)).
- Writes or arbitrary execution.
