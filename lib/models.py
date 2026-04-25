"""Pydantic models used across the competitor-landscape pipeline."""

from pydantic import BaseModel, Field


class PipelineStep(BaseModel):
    """A single drug-development phase step loaded from the input CSV."""

    phase: str
    step: str
    activities: str


class PageFetchResult(BaseModel):
    """A normalized result from page fetching and extraction-quality assessment."""

    text: str = ""
    extraction_status: str = "empty"
    blocked_reason: str = ""
    render_mode: str = "trafilatura"
    quality_score: float = 0.0


class EvidenceDoc(BaseModel):
    """A normalized evidence document gathered from search results or fetched pages."""

    phase: str
    step: str
    activities_signature: str = ""
    query: str
    url: str
    title: str = ""
    snippet: str = ""
    text: str = ""
    company_name: str = ""
    source_type: str = "web_search"
    extraction_status: str = "not_fetched"
    blocked_reason: str = ""
    render_mode: str = "trafilatura"
    quality_score: float = 0.0


class Candidate(BaseModel):
    """A candidate competitor extracted from step-level evidence."""

    name: str
    rationale: str
    vertical_or_horizontal_guess: str = ""
    confidence: float = 0.5
    evidence_urls: list[str] = Field(default_factory=list)
    source: str = "discovered"


class TaxonomyAssignment(BaseModel):
    """A controlled-taxonomy assignment for a pipeline step or company capability."""

    primary_phase: str = ""
    primary_subcategory: str = ""
    phase_labels: list[str] = Field(default_factory=list)
    subcategory_labels: list[str] = Field(default_factory=list)
    rationale: str = ""


class CompanyProfile(BaseModel):
    """A normalized company profile used for cross-step competitor comparison."""

    name: str
    vertical_or_horizontal: str
    funding: str = ""
    funding_rounds: str = ""
    employees: str = ""
    founded: str = ""
    headquarters: str = ""
    presence: list[str] = Field(default_factory=list)
    website: str = ""
    specialization: str = ""
    explicit_agentic_posture: str = "unclear"
    confidence: float = 0.5
    evidence_urls: list[str] = Field(default_factory=list)
    logo_path: str = ""
    taxonomy_primary_phase: str = ""
    taxonomy_primary_subcategory: str = ""
    taxonomy_phase_labels: list[str] = Field(default_factory=list)
    taxonomy_subcategory_labels: list[str] = Field(default_factory=list)


class VerificationResult(BaseModel):
    """A verification decision for whether a company belongs in a specific step."""

    include: bool
    confidence: float
    reason: str


class UserSeedCompany(BaseModel):
    """A user-provided company record loaded from the optional seed-company CSV."""

    company_name: str
    classification: str = ""
    website: str = ""
    phase: str = ""
    step: str = ""
    notes: str = ""
    funding: str = ""
    funding_rounds: str = ""
    employees: str = ""
    founded: str = ""
    headquarters: str = ""
    presence: str = ""


class CompanyResearchRequest(BaseModel):
    """A normalized research request that can be passed to the research and enrichment agents."""

    company_name: str
    classification: str = ""
    website: str = ""
    phase: str = ""
    step: str = ""
    notes: str = ""
    known_fields: dict[str, str] = Field(default_factory=dict)
    preferred_domains: list[str] = Field(default_factory=list)
    query_hints: list[str] = Field(default_factory=list)