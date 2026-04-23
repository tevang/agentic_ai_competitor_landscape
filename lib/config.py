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
    chroma_path: str
    chroma_collection_name: str


class RuntimeConfig(StrictConfigModel):
    """Top-level runtime controls for the orchestrated analysis."""

    max_steps: int = 5
    max_candidates_per_step: int = 10
    verbose: bool = True


class OpenAIConfig(StrictConfigModel):
    """Configuration for OpenAI Responses API calls."""

    api_key_env_var: str = "OPENAI_API_KEY"
    model: str = "gpt-5"
    retry_attempts: int = 3
    retry_wait_min_seconds: int = 1
    retry_wait_max_seconds: int = 15


class TavilyConfig(StrictConfigModel):
    """Configuration for Tavily web search and downstream text fetching."""

    api_key_env_var: str = "TAVILY_API_KEY"
    topic: str = "general"
    search_depth: str = "advanced"
    chunks_per_source: int | None = 3
    default_max_results: int = 5
    step_search_max_results: int = 5
    company_search_max_results: int = 5
    queries_per_step: int = 5
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
    step_fetch_text_for_top_n_results: int = 3
    company_fetch_text_for_top_n_results: int = 3
    page_text_char_limit: int = 2500
    trafilatura_include_links: bool = False
    trafilatura_include_images: bool = False
    search_cache_size: int = 512
    fetch_cache_size: int = 1024


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
    """Configuration for report previews and presentation output sizes."""

    matrix_head_rows: int = 20
    profile_head_rows: int = 20
    gap_head_rows: int = 12
    slide_gap_head_rows: int = 10
    slide_count: int = 10


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
    openai: OpenAIConfig
    tavily: TavilyConfig
    rag: RagConfig
    react: ReactConfig
    dedupe: DedupeConfig
    reporting: ReportingConfig
    scoring: ScoringConfig


def load_config(path: str | Path) -> AppConfig:
    """Load the YAML configuration file and return a validated config object."""

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        data: dict[str, Any] = yaml.safe_load(handle) or {}

    return AppConfig(**data)