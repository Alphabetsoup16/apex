from __future__ import annotations

import re

_SECRET_PATTERNS: list[re.Pattern[str]] = [
    # Common LLM provider API keys / tokens (heuristic)
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\b(?!\s)AKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b"),
    re.compile(r"\b(ghp|gho|ghu|ghs)_[0-9A-Za-z]{20,}\b"),
    # Generic “password=...”, “token=...”
    re.compile(r"(?i)\b(password|pass|token|secret|apikey|api_key)\s*=\s*['\"][^'\"]+['\"]"),
]


def redact_secrets(text: str) -> str:
    """
    Best-effort redaction for sensitive strings before they reach the LLM or logs.

    This is intentionally heuristic; it should not be treated as a security boundary.
    """

    redacted = text
    for pat in _SECRET_PATTERNS:
        redacted = pat.sub("[REDACTED]", redacted)
    return redacted
