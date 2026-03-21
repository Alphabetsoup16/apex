"""Unit tests for ``apex.config.env``."""

from __future__ import annotations

import pytest

from apex.config import env as env_mod


def test_env_str(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APEX_TEST_STR", raising=False)
    assert env_mod.env_str("APEX_TEST_STR") == ""
    monkeypatch.setenv("APEX_TEST_STR", "  x  ")
    assert env_mod.env_str("APEX_TEST_STR") == "x"


def test_env_str_or_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APEX_TEST_SN", raising=False)
    assert env_mod.env_str_or_none("APEX_TEST_SN") is None
    monkeypatch.setenv("APEX_TEST_SN", "  ")
    assert env_mod.env_str_or_none("APEX_TEST_SN") is None
    monkeypatch.setenv("APEX_TEST_SN", "ok")
    assert env_mod.env_str_or_none("APEX_TEST_SN") == "ok"


def test_env_bool_tri_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APEX_TEST_BOOL", raising=False)
    assert env_mod.env_bool("APEX_TEST_BOOL", default=True) is True
    assert env_mod.env_bool("APEX_TEST_BOOL", default=False) is False

    monkeypatch.setenv("APEX_TEST_BOOL", "1")
    assert env_mod.env_bool("APEX_TEST_BOOL", default=False) is True
    monkeypatch.setenv("APEX_TEST_BOOL", "false")
    assert env_mod.env_bool("APEX_TEST_BOOL", default=True) is False

    monkeypatch.setenv("APEX_TEST_BOOL", "maybe")
    assert env_mod.env_bool("APEX_TEST_BOOL", default=True) is True
    assert env_mod.env_bool("APEX_TEST_BOOL", default=False) is False


def test_env_int(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APEX_TEST_INT", raising=False)
    assert env_mod.env_int("APEX_TEST_INT", 7) == 7
    monkeypatch.setenv("APEX_TEST_INT", "notint")
    assert env_mod.env_int("APEX_TEST_INT", 7) == 7
    monkeypatch.setenv("APEX_TEST_INT", "42")
    assert env_mod.env_int("APEX_TEST_INT", 7) == 42


def test_env_int_nonnegative_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APEX_TEST_NNC", "-1")
    assert env_mod.env_int_nonnegative_clamped("APEX_TEST_NNC", default=3, ceiling=10) == 0
    monkeypatch.setenv("APEX_TEST_NNC", "99")
    assert env_mod.env_int_nonnegative_clamped("APEX_TEST_NNC", default=3, ceiling=10) == 10


def test_env_positive_int_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APEX_TEST_PIC", raising=False)
    assert env_mod.env_positive_int_clamped("APEX_TEST_PIC", default=100, ceiling=200) == 100
    monkeypatch.setenv("APEX_TEST_PIC", "bad")
    assert env_mod.env_positive_int_clamped("APEX_TEST_PIC", default=100, ceiling=200) == 100
    monkeypatch.setenv("APEX_TEST_PIC", "250")
    assert env_mod.env_positive_int_clamped("APEX_TEST_PIC", default=100, ceiling=200) == 200
    monkeypatch.setenv("APEX_TEST_PIC", "0")
    assert env_mod.env_positive_int_clamped("APEX_TEST_PIC", default=50, ceiling=200) == 1
