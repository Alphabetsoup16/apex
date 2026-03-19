from __future__ import annotations

"""
Backwards-compatible import surface.

The implementation lives in `apex/llm/` (providers + loader). This file remains
to avoid breaking existing imports.
"""

from apex.llm.loader import load_llm_client_from_env


