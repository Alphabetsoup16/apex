from __future__ import annotations

import apex.__main__ as apex_main


def test_cli_init_show_dispatches_to_cmd_show(monkeypatch) -> None:
    called: list[str] = []

    monkeypatch.setattr(apex_main.llm_cmd, "cmd_show", lambda: called.append("show"))

    apex_main.main(["init", "show"])
    assert called == ["show"]


def test_cli_setup_clear_dispatches_to_cmd_clear(monkeypatch) -> None:
    called: list[str] = []

    monkeypatch.setattr(apex_main.llm_cmd, "cmd_clear", lambda: called.append("clear"))

    apex_main.main(["setup", "clear"])
    assert called == ["clear"]


def test_cli_init_default_dispatches_to_cmd_setup(monkeypatch) -> None:
    called: list[str] = []

    monkeypatch.setattr(apex_main.llm_cmd, "cmd_setup", lambda: called.append("setup"))

    apex_main.main(["init"])
    assert called == ["setup"]


def test_cli_ledger_summary_dispatches(monkeypatch) -> None:
    from apex.cli import ledger_cmd

    called: list[str] = []

    monkeypatch.setattr(ledger_cmd, "cmd_ledger_summary", lambda: called.append("summary"))

    apex_main.main(["ledger"])
    apex_main.main(["ledger", "summary"])
    assert called == ["summary", "summary"]
