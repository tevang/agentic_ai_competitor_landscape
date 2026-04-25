"""Configuration models and YAML loading utilities for the project."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class StrictConfigModel(BaseModel):
    """Base class for strict configuration models loaded from YAML."""

    model_config = ConfigDict(extra="forbid")


class PathsConfig(StrictConfigModel):
    """Filesystem paths used by the application."""

    pipeline_csv: str
    seed_companies_csv: str | None = None
    chroma_path: str
    chroma_collection_name: str
    reports_dir: str = "reports"
    logos_subdir: str = "logos"


class RuntimeConfig(StrictConfigModel):
    """Top-level runtime controls for the orchestrated analysis."""

    max_steps: int = 5
    max_candidates_per_step: int = 10
    verbose: bool = True
    process_user_seed_companies_first: bool = True
    match_seed_companies_to_steps: bool = True
    run_label: str | None = None


class UserInputsConfig(StrictConfigModel):
    """Configuration for optional user-provided company inputs."""

    seed_companies_enabled: bool = True
    seed_companies_required: bool = False


class OpenAIConfig(StrictConfigModel):
    """Configuration for OpenAI Responses API calls."""

    api_key_env_var: str = "OPENAI_API_KEY"
    model: str = "gpt-5"
    retry_attempts: int = 3
    retry_wait_min_seconds: int = 1
    retry_wait_max_seconds: int = 15


class SearchRigorProfileConfig(StrictConfigModel):
    """A preset bundle controlling search breadth, fetched text, and company-query counts."""

    search_depth: str = "basic"
    chunks_per_source: int | None = 1
    default_max_results: int = 3
    step_search_max_results: int = 3
    company_search_max_results: int = 4
    queries_per_step: int = 3
    queries_per_company: int = 4
    step_fetch_text_for_top_n_results: int = 1
    company_fetch_text_for_top_n_results: int = 2
    page_text_char_limit: int = 1200


class TavilyConfig(StrictConfigModel):
    """Configuration for Tavily web search and downstream text fetching."""

    api_key_env_var: str = "TAVILY_API_KEY"
    topic: str = "general"
    auto_parameters: bool = False
    exact_match: bool = False
    include_answer: bool | str = False
    include_raw_content: bool | str = False
    include_images: bool = False
    include_image_descriptions: bool = False
    include_favicon: bool = False
    include_usage: bool = False
    include_domains: list[str] = Field(default_factory=list)
    exclude_domains: list[str] = Field(default_factory=list)
    country: str | None = None
    time_range: str | None = None
    days: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    trafilatura_include_links: bool = False
    trafilatura_include_images: bool = False
    search_cache_size: int = 512
    fetch_cache_size: int = 1024
    profiles: dict[str, SearchRigorProfileConfig] = Field(default_factory=dict)


class CompanyDataSourcesConfig(StrictConfigModel):
    """Lists of domains that should be prioritized for specific company facts."""

    funding: list[str] = Field(default_factory=list)
    funding_rounds: list[str] = Field(default_factory=list)
    employees: list[str] = Field(default_factory=list)
    founded: list[str] = Field(default_factory=list)
    headquarters: list[str] = Field(default_factory=list)
    presence: list[str] = Field(default_factory=list)

    def urls_for_field(self, field_name: str) -> list[str]:
        """Return the configured source URLs for a specific company fact field."""

        return list(getattr(self, field_name, []))


class SearchProtocolConfig(StrictConfigModel):
    """Controls cache reuse and the active web-search rigor preset."""

    active_rigor: str = "standard"
    reuse_existing_step_evidence: bool = True
    reuse_existing_company_evidence: bool = True
    reuse_existing_profiles: bool = True
    reuse_existing_query_plans: bool = True
    reuse_existing_candidates: bool = True
    reuse_existing_verifications: bool = True
    skip_web_if_existing_step_docs_at_least: int = 12
    skip_web_if_existing_company_docs_at_least: int = 10
    skip_llm_if_existing_profile_confidence_at_least: float = 0.75
    skip_llm_if_existing_verification_confidence_at_least: float = 0.75
    prefer_cached_url_text: bool = True
    allow_web_search_after_cache_hit: bool = False


class RetrievalGuardConfig(StrictConfigModel):
    """Configuration for safe extraction-quality checks and optional browser-render fallback."""

    enabled: bool = True
    min_clean_text_chars: int = 350
    detect_cookie_banners: bool = True
    detect_consent_walls: bool = True
    detect_captcha_pages: bool = True
    detect_challenge_pages: bool = True
    detect_javascript_placeholders: bool = True
    strip_cookie_banner_lines: bool = True
    safe_fail_on_protected_pages: bool = True
    allow_browser_render_fallback: bool = True
    browser_render_timeout_ms: int = 15_000
    browser_wait_until: str = "domcontentloaded"
    browser_headless: bool = True
    browser_user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )


class TaxonomyConfig(StrictConfigModel):
    """Configuration for controlled taxonomy enforcement."""

    enforce: bool = True
    include_in_planner_prompt: bool = True
    include_in_verification_prompt: bool = True
    canonical_phases: list[str] = Field(
        default_factory=lambda: [
            "Discovery",
            "Preclinical",
            "Clinical",
            "Regulatory",
            "Manufacturing",
            "Pharmacovigilance",
            "Commercial/Lifecycle",
        ]
    )


class RagConfig(StrictConfigModel):
    """Configuration for the evidence store and retrieval context sizes."""

    chroma_document_char_limit: int = 4000
    store_query_n_results: int = 8
    enrichment_rag_results: int = 10
    verification_rag_results: int = 8
    step_context_limit: int = 12
    step_context_chars_per_item: int = 900
    enrichment_context_limit: int = 14
    enrichment_context_chars_per_item: int = 900
    verification_context_limit: int = 8
    verification_context_chars_per_item: int = 900


class ReactConfig(StrictConfigModel):
    """Configuration for the lightweight ReAct refinement loop."""

    enable_refinement_pass: bool = True
    min_candidates_before_refine: int = 3
    refinement_query_count: int = 5


class DedupeConfig(StrictConfigModel):
    """Configuration for fuzzy deduplication of extracted company names."""

    fuzzy_threshold: int = 94


class ReportingConfig(StrictConfigModel):
    """Configuration for report previews and markdown output files."""

    matrix_head_rows: int = 20
    profile_head_rows: int = 20
    gap_head_rows: int = 12
    slide_gap_head_rows: int = 10
    slide_count: int = 10
    write_markdown_files: bool = True
    report_file_name: str = "competitor_landscape_report.md"
    gap_memo_file_name: str = "gap_memo.md"
    slide_outline_file_name: str = "presentation_outline.md"
    fact_analysis_file_name: str = "fact_driven_analysis.md"
    critical_review_file_name: str = "critical_review.md"
    include_logo_gallery: bool = True


class LogosConfig(StrictConfigModel):
    """Configuration for downloading company logos into the report directory."""

    download_enabled: bool = True
    request_timeout_seconds: int = 15
    min_image_bytes: int = 200
    max_image_bytes: int = 5_000_000
    try_logo_img: bool = True
    try_og_image: bool = True
    fallback_to_favicon: bool = True
    allowed_extensions: list[str] = Field(
        default_factory=lambda: [".png", ".jpg", ".jpeg", ".svg", ".webp", ".ico"]
    )


class ScoringConfig(StrictConfigModel):
    """Configuration for whitespace and saturation scoring."""

    explicit_agentic_weight: float = 0.5
    vertical_weight: float = 0.35
    whitespace_baseline: float = 4.5
    default_pain_weight: float = 2.5
    pain_weights: dict[str, float] = Field(default_factory=dict)
    regulatory_tailwind: dict[str, float] = Field(default_factory=dict)


class AppConfig(StrictConfigModel):
    """Root configuration object for the full application."""

    paths: PathsConfig
    runtime: RuntimeConfig
    user_inputs: UserInputsConfig
    company_data_sources: CompanyDataSourcesConfig
    openai: OpenAIConfig
    search_protocol: SearchProtocolConfig
    retrieval_guard: RetrievalGuardConfig
    taxonomy: TaxonomyConfig
    tavily: TavilyConfig
    rag: RagConfig
    react: ReactConfig
    dedupe: DedupeConfig
    reporting: ReportingConfig
    logos: LogosConfig
    scoring: ScoringConfig

    def get_active_search_profile(self) -> SearchRigorProfileConfig:
        """Return the configured active search-rigor preset."""

        profile_name = self.search_protocol.active_rigor
        if profile_name not in self.tavily.profiles:
            available = ", ".join(sorted(self.tavily.profiles.keys()))
            raise KeyError(f"Unknown search rigor profile '{profile_name}'. Available: {available}")
        return self.tavily.profiles[profile_name]


def load_config(path: str | Path) -> AppConfig:
    """Load the YAML configuration file and return a validated config object."""

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        data: dict[str, Any] = yaml.safe_load(handle) or {}

    return AppConfig(**data)