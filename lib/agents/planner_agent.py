"""Planning agent that converts a pipeline step into a concrete search plan."""

from lib.config import AppConfig
from lib.llm import LLM
from lib.models import Candidate, PipelineStep
from lib.retrieval.evidence_store import EvidenceStore


class PlannerAgent:
    """Generate initial and refinement query plans for each pipeline step."""

    def __init__(self, llm: LLM, config: AppConfig, store: EvidenceStore) -> None:
        """Store dependencies required to generate and cache search plans."""

        self.llm = llm
        self.config = config
        self.store = store

    def build_query_plan(self, step: PipelineStep) -> list[str]:
        """Generate or reuse the initial set of web queries for a pipeline step."""

        if self.config.search_protocol.reuse_existing_query_plans:
            cached = self.store.get_query_plan(step.phase, step.step)
            if cached:
                return cached[: self.config.get_active_search_profile().queries_per_step]

        query_count = self.config.get_active_search_profile().queries_per_step
        prompt = f"""
You are a search-planning agent for biotech competitive intelligence.

STEP:
Phase: {step.phase}
Step: {step.step}
Activities: {step.activities}

Task:
Generate {query_count} web search queries to find companies that build, market, or materially deploy AI or agentic solutions relevant to this exact step.

Requirements:
- Include one query using "agentic AI" or "AI scientist" language.
- Include one query using broader "AI platform" or "machine learning" language.
- Include one query aimed at startup/vendor discovery.
- Include one query aimed at product pages / solution pages.
- Focus on biotech / pharma / drug discovery / clinical / regulatory relevance.

Return JSON:
{{
  "queries": ["...", "...", "..."]
}}
"""
        data = self.llm.ask_json(prompt)
        queries = [query.strip() for query in data.get("queries", []) if query.strip()][:query_count]
        self.store.save_query_plan(step.phase, step.step, queries)
        return queries

    def refine_queries(self, step: PipelineStep, candidates: list[Candidate]) -> list[str]:
        """Produce a lightweight refinement pass when the first search pass is too sparse."""

        seen = ", ".join(candidate.name for candidate in candidates[:5]) or "none"
        templates = [
            f'"{step.step}" biotech AI startup',
            f'"{step.step}" pharma AI platform company',
            f'"{step.phase}" "{step.step}" machine learning vendor',
            f'"{step.step}" "drug development" "AI" company',
            f'"{step.step}" "agentic AI" pharma {seen}',
        ]
        return templates[: self.config.react.refinement_query_count]