# Documentation

- [Architecture](architecture.md)
- [Flow chart](flow.md)
- [Pipeline steps (adding stages)](pipeline-steps.md)
- [Tool interface contract](tool-interface.md)
- [Verification semantics](verification.md)
- [Code execution backend contract](code-execution.md)
- [Safety & auditing](safety.md)
- [Configuration](configuration.md)

## Tests vs docs

- Behavioral tests: `tests/` (patch at the import site used by the module under test; see [architecture.md](architecture.md)).
- Declarative pipeline regressions: `tests/eval/` (verdict + ordered `pipeline_steps` ids).

