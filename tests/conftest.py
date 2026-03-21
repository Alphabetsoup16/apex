"""
Pytest defaults: keep tests from writing the real ~/.apex/ledger.sqlite3.

Ledger tests that need recording must clear ``APEX_LEDGER_DISABLED`` and set ``APEX_LEDGER_PATH``.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_run_ledger_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APEX_LEDGER_DISABLED", "1")


@pytest.fixture(autouse=True)
def _reset_run_concurrency_gate() -> None:
    """Avoid cross-test leakage when ``APEX_MAX_CONCURRENT_RUNS`` is used."""
    from apex.runtime.run_limits import reset_run_gate_for_tests

    reset_run_gate_for_tests()
    yield
    reset_run_gate_for_tests()
