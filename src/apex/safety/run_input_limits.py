"""
Shared string-field limits for ``apex_run`` inputs (MCP, CLI, embedders).

Caps are defined in ``apex.config.constants`` (``MCP_MAX_*``). Rejecting oversize
or NUL-containing input avoids accidental memory pressure and keeps operator
expectations aligned across entrypoints.
"""

from __future__ import annotations

import re
from typing import Any

from apex.config.constants import (
    MCP_CORRELATION_ID_MAX_LEN,
    MCP_MAX_DIFF_CHARS,
    MCP_MAX_FINDINGS_POLICY_ENTRY_CHARS,
    MCP_MAX_FINDINGS_POLICY_ITEMS,
    MCP_MAX_KNOWN_GOOD_BASELINE_CHARS,
    MCP_MAX_LANGUAGE_CHARS,
    MCP_MAX_OUTPUT_MODE_CHARS,
    MCP_MAX_PROMPT_CHARS,
    MCP_MAX_REPO_CONVENTIONS_CHARS,
    MCP_MAX_SUPPLEMENTARY_CONTEXT_CHARS,
)

_CORRELATION_ID_RE = re.compile(
    rf"^[a-zA-Z0-9._-]{{1,{MCP_CORRELATION_ID_MAX_LEN}}}$",
)


def _reject_nul(name: str, value: str | None) -> str | None:
    if value is not None and "\x00" in value:
        return f"{name} must not contain NUL bytes"
    return None


def _reject_len(name: str, value: str | None, *, max_chars: int) -> str | None:
    if value is None:
        return None
    if len(value) > max_chars:
        return f"{name} exceeds {max_chars} characters"
    return None


def validate_correlation_id(correlation_id: str | None) -> str | None:
    """
    Return an error message if ``correlation_id`` is invalid, else ``None``.

    ``None`` / blank means "no correlation id" (valid).
    """
    if correlation_id is None:
        return None
    s = correlation_id.strip()
    if not s:
        return None
    if len(s) > MCP_CORRELATION_ID_MAX_LEN:
        return "correlation_id exceeds maximum length"
    if not _CORRELATION_ID_RE.match(s):
        return "correlation_id must be alphanumeric plus ._- only"
    return None


def parse_findings_policy_overrides(
    findings_ignore_types: list[str] | None,
    findings_ignore_severities: list[str] | None,
) -> tuple[str | None, tuple[str, ...], tuple[str, ...]]:
    """
    Validate optional per-run findings policy lists.

    Returns ``(error, types_tuple, severities_tuple)``. ``error`` is a human message
    when invalid; otherwise ``None``.
    """

    def _one(
        label: str, raw: list[str] | None
    ) -> tuple[str | None, tuple[str, ...]]:
        if raw is None:
            return None, ()
        if len(raw) > MCP_MAX_FINDINGS_POLICY_ITEMS:
            return f"{label} exceeds {MCP_MAX_FINDINGS_POLICY_ITEMS} entries", ()
        out: list[str] = []
        for i, item in enumerate(raw):
            s = str(item).strip()
            if not s:
                return f"{label}[{i}] is empty", ()
            if "\x00" in s:
                return f"{label} entries must not contain NUL bytes", ()
            if len(s) > MCP_MAX_FINDINGS_POLICY_ENTRY_CHARS:
                return (
                    f"{label}[{i}] exceeds {MCP_MAX_FINDINGS_POLICY_ENTRY_CHARS} characters",
                    (),
                )
            out.append(s)
        return None, tuple(out)

    et, tt = _one("findings_ignore_types", findings_ignore_types)
    if et:
        return et, (), ()
    es, st = _one("findings_ignore_severities", findings_ignore_severities)
    if es:
        return es, (), ()
    return None, tt, st


def validate_run_inputs(
    *,
    prompt: str,
    diff: str | None,
    repo_conventions: str | None,
    known_good_baseline: str | None,
    language: str | None,
    output_mode: str,
    supplementary_context: str | None,
) -> str | None:
    """Return first validation error message, or ``None`` if all inputs are acceptable."""
    checks: list[tuple[str, Any]] = [
        ("prompt", _reject_nul("prompt", prompt)),
        ("prompt", _reject_len("prompt", prompt, max_chars=MCP_MAX_PROMPT_CHARS)),
        ("diff", _reject_nul("diff", diff)),
        ("diff", _reject_len("diff", diff, max_chars=MCP_MAX_DIFF_CHARS)),
        ("repo_conventions", _reject_nul("repo_conventions", repo_conventions)),
        (
            "repo_conventions",
            _reject_len(
                "repo_conventions",
                repo_conventions,
                max_chars=MCP_MAX_REPO_CONVENTIONS_CHARS,
            ),
        ),
        ("known_good_baseline", _reject_nul("known_good_baseline", known_good_baseline)),
        (
            "known_good_baseline",
            _reject_len(
                "known_good_baseline",
                known_good_baseline,
                max_chars=MCP_MAX_KNOWN_GOOD_BASELINE_CHARS,
            ),
        ),
        ("language", _reject_nul("language", language)),
        ("language", _reject_len("language", language, max_chars=MCP_MAX_LANGUAGE_CHARS)),
        ("output_mode", _reject_nul("output_mode", output_mode)),
        (
            "output_mode",
            _reject_len("output_mode", output_mode, max_chars=MCP_MAX_OUTPUT_MODE_CHARS),
        ),
        ("supplementary_context", _reject_nul("supplementary_context", supplementary_context)),
        (
            "supplementary_context",
            _reject_len(
                "supplementary_context",
                supplementary_context,
                max_chars=MCP_MAX_SUPPLEMENTARY_CONTEXT_CHARS,
            ),
        ),
    ]
    for _, err in checks:
        if err:
            return err
    return None


validate_run_tool_inputs = validate_run_inputs
