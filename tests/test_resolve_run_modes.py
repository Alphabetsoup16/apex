from __future__ import annotations

from apex.pipeline import resolve_run_modes


def test_resolve_auto_uses_inference() -> None:
    actual, inferred = resolve_run_modes(prompt="implement a python function", mode="auto")
    assert inferred == "code"
    assert actual == "code"


def test_resolve_explicit_overrides() -> None:
    actual, inferred = resolve_run_modes(prompt="implement a python function", mode="text")
    assert inferred == "code"
    assert actual == "text"
