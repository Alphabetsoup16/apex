from __future__ import annotations

from pathlib import Path
from typing import Any

from apex.repo_context.config import RepoContextConfig
from apex.repo_context.policy import is_root_relative_posix_path, resolve_confined

SCHEMA = "apex.repo_context/v1"
READ_SCHEMA = "apex.repo_context.read/v1"
GLOB_SCHEMA = "apex.repo_context.glob/v1"


def _disabled_payload(*, reason: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "enabled": False,
        "detail": reason,
    }


def read_disabled_payload() -> dict[str, Any]:
    return {
        "schema": READ_SCHEMA,
        "enabled": False,
        "ok": False,
        "error": "repo_context_disabled",
        "detail": "Set APEX_REPO_CONTEXT_ROOT (see docs/repo-context.md).",
    }


def glob_disabled_payload() -> dict[str, Any]:
    return {
        "schema": GLOB_SCHEMA,
        "enabled": False,
        "ok": False,
        "error": "repo_context_disabled",
        "matches": [],
    }


def status_payload(cfg: RepoContextConfig | None) -> dict[str, Any]:
    if cfg is None:
        return _disabled_payload(
            reason="Set APEX_REPO_CONTEXT_ROOT or unset APEX_REPO_CONTEXT_DISABLED.",
        )
    root_r = cfg.root.resolve()
    exists = root_r.is_dir()
    return {
        "schema": SCHEMA,
        "enabled": True,
        "root": str(root_r),
        "root_exists": exists,
        "max_file_bytes": cfg.max_file_bytes,
        "max_glob_results": cfg.max_glob_results,
        "max_pattern_len": cfg.max_pattern_len,
        "detail": None if exists else "Root path is not a directory.",
    }


def read_file_payload(cfg: RepoContextConfig, relative_path: str) -> dict[str, Any]:
    if not cfg.root.resolve().is_dir():
        return {
            "schema": READ_SCHEMA,
            "enabled": True,
            "ok": False,
            "error": "repo_root_invalid",
            "detail": "APEX_REPO_CONTEXT_ROOT is not a directory.",
        }

    target = resolve_confined(cfg.root, relative_path)
    if target is None:
        return {
            "schema": READ_SCHEMA,
            "enabled": True,
            "ok": False,
            "error": "path_not_allowed",
            "detail": "Path must be root-relative with no .. segments.",
        }
    if not target.is_file():
        return {
            "schema": READ_SCHEMA,
            "enabled": True,
            "ok": False,
            "error": "not_a_file",
            "detail": str(target.relative_to(cfg.root.resolve())),
        }

    cap = cfg.max_file_bytes
    try:
        with target.open("rb") as fh:
            data = fh.read(cap + 1)
    except OSError as e:
        return {
            "schema": READ_SCHEMA,
            "enabled": True,
            "ok": False,
            "error": "read_error",
            "detail": type(e).__name__,
        }

    truncated = len(data) > cap
    blob = data[:cap]
    text = blob.decode("utf-8", errors="replace")
    rel = str(target.relative_to(cfg.root.resolve()))
    return {
        "schema": READ_SCHEMA,
        "enabled": True,
        "ok": True,
        "relative_path": rel,
        "content": text,
        "byte_length": len(blob),
        "truncated": truncated,
        "encoding": "utf-8",
        "encoding_errors": "replace",
    }


def glob_payload(cfg: RepoContextConfig, pattern: str) -> dict[str, Any]:
    if not cfg.root.resolve().is_dir():
        return {
            "schema": GLOB_SCHEMA,
            "enabled": True,
            "ok": False,
            "error": "repo_root_invalid",
            "matches": [],
        }

    if len(pattern) > cfg.max_pattern_len:
        return {
            "schema": GLOB_SCHEMA,
            "enabled": True,
            "ok": False,
            "error": "pattern_too_long",
            "matches": [],
        }
    if not is_root_relative_posix_path(pattern):
        return {
            "schema": GLOB_SCHEMA,
            "enabled": True,
            "ok": False,
            "error": "pattern_not_allowed",
            "matches": [],
        }

    root_r = cfg.root.resolve()
    norm_pat = pattern.replace("\\", "/").strip()
    paths: list[Path] = []
    truncated = False
    try:
        for p in root_r.glob(norm_pat):
            if not p.is_file():
                continue
            try:
                p.resolve().relative_to(root_r)
            except ValueError:
                continue
            paths.append(p)
            if len(paths) > cfg.max_glob_results:
                truncated = True
                break
    except OSError as e:
        return {
            "schema": GLOB_SCHEMA,
            "enabled": True,
            "ok": False,
            "error": "glob_error",
            "detail": type(e).__name__,
            "matches": [],
        }

    paths = paths[: cfg.max_glob_results]
    matches: list[dict[str, Any]] = []
    for p in paths:
        rel = str(p.resolve().relative_to(root_r))
        try:
            sz = p.stat().st_size
        except OSError:
            sz = None
        matches.append({"relative_path": rel, "size_bytes": sz})

    return {
        "schema": GLOB_SCHEMA,
        "enabled": True,
        "ok": True,
        "pattern": norm_pat,
        "matches": matches,
        "truncated": truncated,
        "limit": cfg.max_glob_results,
    }
