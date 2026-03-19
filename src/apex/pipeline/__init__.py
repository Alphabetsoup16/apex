"""
APEX verification pipeline (light layer by default).

- ``helpers``: shared utilities (mode inference, bundles, baseline similarity).
- ``text_mode`` / ``code_mode``: mode-specific flows (ensemble → safety → review).
- ``run``: ``apex_run`` entrypoint.

Optional sandbox execution for code lives in ``code_mode`` behind ``code_ground_truth``;
the execution client contract remains under ``apex.code_ground_truth``.
"""

from apex.pipeline.run import apex_run

__all__ = ["apex_run"]
