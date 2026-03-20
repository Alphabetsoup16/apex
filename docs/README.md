# Documentation

- [Architecture](architecture.md)
- [Flow chart](flow.md)
- [Pipeline steps (adding stages)](pipeline-steps.md)
- [Tool interface contract](tool-interface.md)
- [Verification semantics](verification.md)
- [Code execution backend contract](code-execution.md)
- [Safety & auditing](safety.md)
- [Configuration](configuration.md#run-ledger-sqlite) (includes **Run ledger**: SQLite at `~/.apex/ledger.sqlite3`, **`apex ledger summary`**)

## Tests vs docs

- Behavioral tests: `tests/` (patch at the import site used by the module under test; see [architecture.md](architecture.md)).
- Declarative pipeline regressions: `tests/eval/` (verdict + ordered `pipeline_steps` ids).
- Trace contract + telemetry helpers: `tests/test_observability.py` (e.g. `validate_pipeline_steps`, `run_wall_ms` from `timings_ms.total`).
- Run ledger: `tests/test_ledger.py`; `tests/conftest.py` sets `APEX_LEDGER_DISABLED=1` so the suite does not write `~/.apex/ledger.sqlite3` unless a test clears it.

