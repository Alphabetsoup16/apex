from __future__ import annotations

from apex.models import AdversarialReview, Finding
from apex.policy import FindingsPolicy


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

    assert [f.evidence for f in out.findings] == ["A"]

