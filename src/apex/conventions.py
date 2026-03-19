from __future__ import annotations

import os
from pathlib import Path


def _read_text_file(path: Path, *, max_chars: int) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    text = text.strip()
    if not text:
        return None
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n[TRUNCATED]"
    return text


def load_effective_conventions(
    *,
    repo_conventions: str | None,
    repo_root: str | None = None,
    max_chars: int = 4000,
) -> str | None:
    """
    Determine the effective conventions for a run.

    Merge order (lowest precedence -> highest):
    1) global/company conventions file (APEX_GLOBAL_CONVENTIONS_PATH)
    2) repo-local conventions file (.apex/conventions.md or .apex/conventions.txt)
    3) explicit `repo_conventions` passed to the tool call

    This keeps APEX usable across many repos without requiring per-repo tool
    configuration, while still allowing per-call overrides.
    """
    parts: list[str] = []

    global_path = os.environ.get("APEX_GLOBAL_CONVENTIONS_PATH", "").strip()
    if global_path:
        p = Path(global_path).expanduser()
        txt = _read_text_file(p, max_chars=max_chars)
        if txt:
            parts.append(txt)

    root = Path(repo_root).expanduser() if repo_root else Path.cwd()
    for rel in (Path(".apex/conventions.md"), Path(".apex/conventions.txt")):
        txt = _read_text_file(root / rel, max_chars=max_chars)
        if txt:
            parts.append(txt)
            break

    if repo_conventions and repo_conventions.strip():
        txt = repo_conventions.strip()
        if len(txt) > max_chars:
            txt = txt[:max_chars] + "\n\n[TRUNCATED]"
        parts.append(txt)

    merged = "\n\n".join(parts).strip()
    return merged or None

