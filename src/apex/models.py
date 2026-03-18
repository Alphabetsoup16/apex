from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Mode = Literal["auto", "text", "code"]
Verdict = Literal["high_verified", "needs_review", "blocked"]


class StrictBaseModel(BaseModel):
    # We validate required structure, but ignore extra fields for robustness
    # against small model formatting variations.
    model_config = ConfigDict(extra="ignore")


class Finding(StrictBaseModel):
    severity: Literal["high", "medium", "low"]
    type: str = Field(
        description="Short finding category, e.g. incorrect_assumption, missing_edge_case"
    )
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = Field(description="Concrete excerpt or mismatch evidence")
    location: str | None = None
    recommendation: str | None = None


class AdversarialReview(StrictBaseModel):
    findings: list[Finding] = Field(default_factory=list)


class TextCompletion(StrictBaseModel):
    answer: str
    key_claims: list[str] = Field(default_factory=list)


class CodeFile(StrictBaseModel):
    path: str
    content: str


class CodeSolution(StrictBaseModel):
    files: list[CodeFile]


class CodeTests(StrictBaseModel):
    files: list[CodeFile]
    test_framework: str = "pytest"


class ExecutionResult(StrictBaseModel):
    pass_: bool = Field(alias="pass")
    stdout: str
    stderr: str
    duration_ms: int = Field(ge=0)


class ApexRunToolResult(StrictBaseModel):
    """
    Tool response wrapper. FastMCP returns JSON-compatible dicts, so we keep
    the response model separate from the user-visible output model.
    """

    verdict: Verdict
    output: str
    metadata: dict = Field(default_factory=dict)
    adversarial_review: AdversarialReview | None = None
    execution: ExecutionResult | None = None

