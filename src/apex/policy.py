from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from apex.models import AdversarialReview, Finding


@dataclass(frozen=True)
class FindingsPolicy:
    """
    Optional policy layer that can filter findings for reporting.

    By default, it does not change anything.
    """

    ignored_types: tuple[str, ...] = ()
    ignored_severities: tuple[str, ...] = ()

    def apply(self, review: AdversarialReview) -> AdversarialReview:
        if not review.findings:
            return review

        filtered: list[Finding] = []
        for f in review.findings:
            if self.ignored_severities and f.severity in self.ignored_severities:
                continue
            if self.ignored_types and f.type in self.ignored_types:
                continue
            filtered.append(f)
        return AdversarialReview(findings=filtered)


def _read_json_file(path: Path) -> dict | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def load_findings_policy(*, repo_root: str | None = None) -> FindingsPolicy:
    """
    Load an optional findings policy.

    Precedence (lowest -> highest):
    1) global/company policy: APEX_GLOBAL_POLICY_PATH (JSON)
    2) repo-local policy: .apex/policy.json
    """
    merged: dict = {}

    global_path = os.environ.get("APEX_GLOBAL_POLICY_PATH", "").strip()
    if global_path:
        data = _read_json_file(Path(global_path).expanduser())
        if isinstance(data, dict):
            merged.update(data)

    root = Path(repo_root).expanduser() if repo_root else Path.cwd()
    data = _read_json_file(root / ".apex/policy.json")
    if isinstance(data, dict):
        merged.update(data)

    ignored_types = tuple(str(x) for x in (merged.get("ignored_types") or []) if str(x).strip())
    ignored_severities = tuple(
        str(x) for x in (merged.get("ignored_severities") or []) if str(x).strip()
    )
    return FindingsPolicy(ignored_types=ignored_types, ignored_severities=ignored_severities)

