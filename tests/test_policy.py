from __future__ import annotations

import json
from pathlib import Path

import pytest

from apex.config.policy import FindingsPolicy, load_findings_policy, merge_findings_policy
from apex.models import AdversarialReview, Finding


def test_findings_policy_filters_by_type_and_severity() -> None:
    review = AdversarialReview(
        findings=[
            Finding(
                severity="high",
                type="security",
                confidence=0.9,
                evidence="A",
                recommendation="fix A",
            ),
            Finding(
                severity="medium",
                type="style",
                confidence=0.9,
                evidence="B",
                recommendation="fix B",
            ),
            Finding(
                severity="low",
                type="performance",
                confidence=0.9,
                evidence="C",
                recommendation="fix C",
            ),
        ]
    )

    p = FindingsPolicy(ignored_types=("style",), ignored_severities=("low",))
    out = p.apply(review)

    # Medium is verdict-relevant and must not be removed even when type is ignored.
    assert [f.evidence for f in out.findings] == ["A", "B"]


def test_findings_policy_never_drops_high_even_when_type_or_severity_ignored() -> None:
    review = AdversarialReview(
        findings=[
            Finding(
                severity="high",
                type="style",
                confidence=0.9,
                evidence="must_stay",
                recommendation="x",
            ),
        ]
    )
    p = FindingsPolicy(ignored_types=("style",), ignored_severities=("high",))
    out = p.apply(review)
    assert len(out.findings) == 1
    assert out.findings[0].evidence == "must_stay"


def test_load_findings_policy_from_repo_file_merges_with_runtime_extras(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    policy_dir = root / ".apex"
    policy_dir.mkdir()
    (policy_dir / "policy.json").write_text(
        json.dumps({"ignored_types": ["from_file"], "ignored_severities": []}),
        encoding="utf-8",
    )
    monkeypatch.chdir(root)
    base = load_findings_policy()
    merged = merge_findings_policy(base, extra_ignored_types=("per_run",))
    assert merged.ignored_types == ("from_file", "per_run")
    assert merged.ignored_severities == ()


def test_merge_findings_policy_unions_without_duplicates() -> None:
    base = FindingsPolicy(ignored_types=("a",), ignored_severities=("low",))
    merged = merge_findings_policy(
        base, extra_ignored_types=("b", "a"), extra_ignored_severities=("info", "low")
    )
    assert merged.ignored_types == ("a", "b")
    assert merged.ignored_severities == ("low", "info")
