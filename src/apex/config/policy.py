from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from apex.config.env import env_str
from apex.models import AdversarialReview, Finding

_VERDICT_RELEVANT_SEVERITIES: frozenset[str] = frozenset({"high", "medium"})


@dataclass(frozen=True)
class FindingsPolicy:
    """
    Optional policy layer that can filter **low** findings for reporting noise.

    ``high`` and ``medium`` findings are always kept: they drive blocking and
    ``high_verified`` eligibility, and must not be stripped by policy configuration.
    """

    ignored_types: tuple[str, ...] = ()
    ignored_severities: tuple[str, ...] = ()

    def apply(self, review: AdversarialReview) -> AdversarialReview:
        if not review.findings:
            return review

        filtered: list[Finding] = []
        for f in review.findings:
            if f.severity in _VERDICT_RELEVANT_SEVERITIES:
                filtered.append(f)
                continue
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

    global_path = env_str("APEX_GLOBAL_POLICY_PATH")
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


def merge_findings_policy(
    base: FindingsPolicy,
    *,
    extra_ignored_types: tuple[str, ...] = (),
    extra_ignored_severities: tuple[str, ...] = (),
) -> FindingsPolicy:
    """
    Merge per-run extras onto a loaded base policy (file/global).

    Order: base entries first, then extras; duplicates are allowed and harmless.
    """

    def _dedupe_tail(a: tuple[str, ...], b: tuple[str, ...]) -> tuple[str, ...]:
        seen = set(a)
        out = list(a)
        for x in b:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return tuple(out)

    return FindingsPolicy(
        ignored_types=_dedupe_tail(base.ignored_types, extra_ignored_types),
        ignored_severities=_dedupe_tail(base.ignored_severities, extra_ignored_severities),
    )
