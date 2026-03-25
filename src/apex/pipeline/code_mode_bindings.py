"""
Indirection for code-mode pipeline collaborators.

Tests should monkeypatch this module so ``code_mode_phases`` sees patched callables
(see CONTRIBUTING.md: patch the binding module).
"""

from __future__ import annotations

from apex.code_ground_truth.executor_client import load_execution_backend_from_env
from apex.generation.ensemble import generate_code_solution_variants, generate_code_tests
from apex.review.adversarial import review_code
from apex.review.inspection import inspect_code_doc_only
from apex.scoring import code_convergence, decide_verdict, select_best_code

__all__ = [
    "code_convergence",
    "decide_verdict",
    "generate_code_solution_variants",
    "generate_code_tests",
    "inspect_code_doc_only",
    "load_execution_backend_from_env",
    "review_code",
    "select_best_code",
]
