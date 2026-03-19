from __future__ import annotations

import re


_COT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("chain_of_thought_phrase", re.compile(r"chain[- ]of[- ]thought", re.IGNORECASE)),
    ("as_an_ai_phrase", re.compile(r"\b(as an ai|i am an ai)\b", re.IGNORECASE)),
    ("thought_colon_marker", re.compile(r"\bthought\s*:", re.IGNORECASE)),
    ("let_s_think", re.compile(r"\blet'?s think\b", re.IGNORECASE)),
]


def audit_chain_of_thought(text: str) -> list[str]:
    """
    Lightweight chain-of-thought leakage auditing.

    We do not attempt to extract or store reasoning; instead we detect a few
    conservative marker patterns and let the caller decide whether to block.
    """
    if not text:
        return []

    findings: list[str] = []
    for name, pat in _COT_PATTERNS:
        if pat.search(text):
            findings.append(name)
    return findings

