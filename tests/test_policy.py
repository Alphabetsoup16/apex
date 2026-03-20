from __future__ import annotations

from apex.config.policy import FindingsPolicy
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
