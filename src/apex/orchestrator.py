"""
Stable import path for the verification entrypoint.

Implementation is organized under ``apex.pipeline`` (light layer: text/code modes;
optional execution isolated in ``code_mode`` + ``apex.code_ground_truth``).
"""

from __future__ import annotations

from apex.pipeline.helpers import infer_mode_from_prompt, validate_code_bundles
from apex.pipeline.run import apex_run

__all__ = ["apex_run", "infer_mode_from_prompt", "validate_code_bundles"]
