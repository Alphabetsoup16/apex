from __future__ import annotations

import pytest

from apex.repo_context.access import glob_payload, read_file_payload, status_payload
from apex.repo_context.config import RepoContextConfig, load_repo_context_config
from apex.repo_context.policy import is_root_relative_posix_path, resolve_confined


@pytest.mark.parametrize(
    ("s", "ok"),
    [
        ("src/a.py", True),
        ("", False),
        ("/etc/passwd", False),
        ("../x", False),
        ("a/../b", False),
    ],
)
def test_is_root_relative(s: str, ok: bool) -> None:
    assert is_root_relative_posix_path(s) is ok


def test_resolve_confined_rejects_escape(tmp_path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    (root / "safe.txt").write_text("ok", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("no", encoding="utf-8")
    try:
        (root / "link").symlink_to(outside)
    except OSError:
        pytest.skip("symlink not supported")
    resolved = resolve_confined(root, "link")
    assert resolved is None


def test_read_file_roundtrip(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APEX_REPO_CONTEXT_DISABLED", raising=False)
    monkeypatch.setenv("APEX_REPO_CONTEXT_ROOT", str(tmp_path))
    monkeypatch.delenv("APEX_REPO_CONTEXT_MAX_FILE_BYTES", raising=False)
    cfg = load_repo_context_config()
    assert cfg is not None
    (tmp_path / "hello.txt").write_text("hi", encoding="utf-8")
    out = read_file_payload(cfg, "hello.txt")
    assert out["ok"] is True
    assert out["content"] == "hi"
    assert out["truncated"] is False


def test_read_file_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APEX_REPO_CONTEXT_ROOT", raising=False)
    assert load_repo_context_config() is None


def test_glob_respects_limit(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APEX_REPO_CONTEXT_DISABLED", raising=False)
    monkeypatch.setenv("APEX_REPO_CONTEXT_ROOT", str(tmp_path))
    monkeypatch.setenv("APEX_REPO_CONTEXT_MAX_GLOB_RESULTS", "2")
    cfg = load_repo_context_config()
    assert cfg is not None
    (tmp_path / "a.py").write_text("1", encoding="utf-8")
    (tmp_path / "b.py").write_text("2", encoding="utf-8")
    (tmp_path / "c.py").write_text("3", encoding="utf-8")
    out = glob_payload(cfg, "*.py")
    assert out["ok"] is True
    assert len(out["matches"]) == 2
    assert out["truncated"] is True


def test_status_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APEX_REPO_CONTEXT_ROOT", raising=False)
    s = status_payload(load_repo_context_config())
    assert s["enabled"] is False


def test_read_not_a_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APEX_REPO_CONTEXT_ROOT", str(tmp_path))
    monkeypatch.delenv("APEX_REPO_CONTEXT_DISABLED", raising=False)
    cfg = load_repo_context_config()
    assert cfg is not None
    (tmp_path / "d").mkdir()
    out = read_file_payload(cfg, "d")
    assert out["ok"] is False
    assert out["error"] == "not_a_file"


def test_manual_config_read_truncated(tmp_path) -> None:
    cfg = RepoContextConfig(
        root=tmp_path,
        max_file_bytes=3,
        max_glob_results=10,
        max_pattern_len=100,
    )
    (tmp_path / "big.txt").write_bytes(b"abcdef")
    out = read_file_payload(cfg, "big.txt")
    assert out["ok"] is True
    assert out["truncated"] is True
    assert out["byte_length"] == 3
