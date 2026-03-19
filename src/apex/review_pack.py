from __future__ import annotations

from apex.models import AdversarialReview, Finding


def _group_findings(findings: list[Finding]) -> dict[str, list[Finding]]:
    buckets: dict[str, list[Finding]] = {"high": [], "medium": [], "low": []}
    for f in findings:
        buckets.setdefault(f.severity, []).append(f)
    return buckets


def _format_finding(f: Finding) -> str:
    parts: list[str] = []
    head = f"**{f.type}** (confidence={f.confidence:.2f})"
    if f.location:
        head += f" — `{f.location}`"
    parts.append(head)
    parts.append(f"- Evidence: {f.evidence}")
    if f.recommendation:
        parts.append(f"- Recommendation: {f.recommendation}")
    return "\n".join(parts)


def build_pr_review_pack(
    *,
    language: str | None,
    verdict: str,
    prompt: str,
    diff: str | None,
    repo_conventions: str | None,
    adversarial: AdversarialReview | None,
    inspection: AdversarialReview | None,
) -> str:
    all_findings: list[Finding] = []
    if adversarial is not None:
        all_findings.extend(adversarial.findings)
    if inspection is not None:
        all_findings.extend(inspection.findings)

    grouped = _group_findings(all_findings)

    lines: list[str] = []
    lines.append("## APEX PR Review Pack")
    lines.append("")
    lines.append(f"- Verdict: **{verdict}**")
    if language:
        lines.append(f"- Language: `{language}`")
    lines.append("")

    if repo_conventions:
        lines.append("### Repo conventions (provided)")
        lines.append(repo_conventions.strip())
        lines.append("")

    if diff:
        lines.append("### Diff (provided)")
        lines.append("```diff")
        lines.append(diff.strip())
        lines.append("```")
        lines.append("")

    lines.append("### Must fix (high)")
    if grouped["high"]:
        for f in grouped["high"]:
            lines.append(f"- {_format_finding(f)}")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("### Should fix (medium)")
    if grouped["medium"]:
        for f in grouped["medium"]:
            lines.append(f"- {_format_finding(f)}")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("### Nice to have (low)")
    if grouped["low"]:
        for f in grouped["low"]:
            lines.append(f"- {_format_finding(f)}")
    else:
        lines.append("- None")
    lines.append("")

    # Keep the original prompt for traceability but avoid bloat.
    lines.append("### Task (truncated)")
    truncated = prompt.strip()
    if len(truncated) > 2000:
        truncated = truncated[:2000] + "\n\n[TRUNCATED]"
    lines.append(truncated)

    return "\n".join(lines).strip() + "\n"
