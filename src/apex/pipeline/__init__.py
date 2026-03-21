"""
APEX verification pipeline (light layer by default).

- ``helpers``: shared utilities (mode inference, bundles, baseline similarity).
- ``step_support``: ``run_async_step`` + ``StepTrace`` (required vs optional behavior).
- ``steps_catalog``: declarative ``PipelineStepSpec`` list per mode (keep in sync with code).
- ``text_mode`` / ``code_mode``: mode-specific flows.
- ``trace_contract``: required keys + ``PipelineStepTraceDict`` for ``pipeline_steps[]``.
- ``observability``: ``finalize_run_result`` → ``metadata.telemetry`` + ``metadata.uncertainty``.
- ``run``: ``apex_run`` entrypoint.
- ``guard_metadata``: blocked-run metadata + ensemble clamp (MCP + ``apex_run`` guards).

See ``docs/pipeline-steps.md`` for how to add new steps.

Optional sandbox execution for code lives in ``code_mode`` behind ``code_ground_truth``;
the execution client contract remains under ``apex.code_ground_truth``.
"""

from apex.pipeline.run import apex_run

__all__ = ["apex_run"]
