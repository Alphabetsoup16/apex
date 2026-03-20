"""
Pytest defaults: keep tests from writing the real ~/.apex/ledger.sqlite3.

Ledger tests that need recording must clear ``APEX_LEDGER_DISABLED`` and set ``APEX_LEDGER_PATH``.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_run_ledger_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APEX_LEDGER_DISABLED", "1")
