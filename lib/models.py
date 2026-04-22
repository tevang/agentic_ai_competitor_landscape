from pydantic import BaseModel, Field
from typing import Any

class PipelineStep(BaseModel):
    """
    Represents a single step in the drug development pipeline.
    """
    phase: str
    step: str
    activities: str


class EvidenceDoc(BaseModel):
    """
    Represents a document collected as evidence during research.
    """
    phase: str
    step: str
    query: str
    url: str
    title: str = ""
    snippet: str = ""
    text: str = ""


class Candidate(BaseModel):
    """
    Represents a candidate company found during the initial research pass.
    """
    name: str
    rationale: str
    vertical_or_horizontal_guess: str = ""
    confidence: float = 0.5
    evidence_urls: list[str] = Field(default_factory=list)


class CompanyProfile(BaseModel):
    """
    A full profile of a company, enriched with more detailed information.
    """
    name: str
    vertical_or_horizontal: str
    funding: str = ""
    employees: str = ""
    founded: str = ""
    headquarters: str = ""
    presence: list[str] = Field(default_factory=list)
    specialization: str = ""
    explicit_agentic_posture: str = "unclear"  # explicit | adjacent | unclear
    confidence: float = 0.5


class VerificationResult(BaseModel):
    """
    The result of verifying whether a company belongs in a specific pipeline step.
    """
    belongs: bool
    confidence: float
    reasoning: str
