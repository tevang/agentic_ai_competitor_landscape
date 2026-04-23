"""Pydantic models used across the competitor-landscape pipeline."""

from pydantic import BaseModel, Field


class PipelineStep(BaseModel):
    """A single drug-development phase step loaded from the input CSV."""

    phase: str
    step: str
    activities: str


class EvidenceDoc(BaseModel):
    """A normalized evidence document gathered from search results or fetched pages."""

    phase: str
    step: str
    query: str
    url: str
    title: str = ""
    snippet: str = ""
    text: str = ""


class Candidate(BaseModel):
    """A candidate competitor extracted from step-level evidence."""

    name: str
    rationale: str
    vertical_or_horizontal_guess: str = ""
    confidence: float = 0.5
    evidence_urls: list[str] = Field(default_factory=list)


class CompanyProfile(BaseModel):
    """A normalized company profile used for cross-step competitor comparison."""

    name: str
    vertical_or_horizontal: str
    funding: str = ""
    employees: str = ""
    founded: str = ""
    headquarters: str = ""
    presence: list[str] = Field(default_factory=list)
    specialization: str = ""
    explicit_agentic_posture: str = "unclear"
    confidence: float = 0.5
    evidence_urls: list[str] = Field(default_factory=list)


class VerificationResult(BaseModel):
    """A verification decision for whether a company belongs in a specific step."""

    include: bool
    confidence: float
    reason: str