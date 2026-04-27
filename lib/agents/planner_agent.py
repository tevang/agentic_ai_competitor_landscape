"""Planning agent that converts a pipeline step into a concrete search plan."""

from lib.config import AppConfig
from lib.discovery.query_factory import build_discovery_queries
from lib.llm import LLM
from lib.models import Candidate, PipelineStep
from lib.retrieval.evidence_store import EvidenceStore
from lib.taxonomy.schema import format_taxonomy_target_for_step
from lib.utils.text_utils import build_step_signature, unique_preserve_order


class PlannerAgent:
    """Generate initial and refinement query plans for each pipeline step."""

    def __init__(self, llm: LLM, config: AppConfig, store: EvidenceStore) -> None:
        """Store dependencies required to generate and cache search plans."""

        self.llm = llm
        self.config = config
        self.store = store

    def build_query_plan(self, step: PipelineStep) -> list[str]:
        """Generate or reuse a broad web-query plan for a pipeline step."""

        step_signature = build_step_signature(step.phase, step.step, step.activities)
        max_total_queries = self.config.discovery.max_total_queries_per_step
        cached: list[str] = []

        if self.config.search_protocol.reuse_existing_query_plans:
            cached = self.store.get_query_plan(step.phase, step.step, step_signature)
            if cached and not self.config.search_protocol.allow_web_search_after_cache_hit:
                return cached[:max_total_queries]

        should_skip_llm_plan = (
            self.config.runtime.analysis_mode == "landscape_scan"
            and self.config.discovery.skip_llm_query_planning_in_landscape_scan
        )

        llm_queries: list[str] = []
        if not should_skip_llm_plan:
            llm_queries = self._build_llm_queries(step)

        auto_queries: list[str] = []
        if self.config.discovery.deterministic_queries_enabled:
            auto_queries = build_discovery_queries(
                step=step,
                max_queries=self.config.discovery.max_auto_queries_per_step,
                max_terms=self.config.discovery.max_search_terms_per_step,
            )

        queries = unique_preserve_order(cached + llm_queries + auto_queries)[:max_total_queries]
        self.store.save_query_plan(step.phase, step.step, step_signature, queries)

        if self.config.runtime.verbosity >= 1:
            print(
                "[planner] "
                f"{step.phase} -> {step.step}: "
                f"queries={len(queries)}, "
                f"llm_queries={len(llm_queries)}, "
                f"auto_queries={len(auto_queries)}, "
                f"mode={self.config.runtime.analysis_mode}"
            )

        return queries

    def refine_queries(self, step: PipelineStep, candidates: list[Candidate]) -> list[str]:
        """Produce a generic refinement pass when the first search pass is too sparse."""

        seen = ", ".join(candidate.name for candidate in candidates[:5]) or "none"
        templates = [
            f'"{step.step}" "AI" "software vendor" pharma',
            f'"{step.step}" "automation platform" "life sciences"',
            f'"{step.step}" "machine learning" "company"',
            f'"{step.step}" "product page" "AI" "biopharma"',
            f'"{step.step}" "agentic AI" pharma {seen}',
            f'"{step.step}" "NLP" "workflow automation" "vendor"',
        ]
        return templates[: self.config.react.refinement_query_count]

    def _build_llm_queries(self, step: PipelineStep) -> list[str]:
        """Build LLM-assisted queries for deeper modes."""

        query_count = self.config.get_active_search_profile().queries_per_step
        if query_count <= 0:
            return []

        taxonomy_target = (
            format_taxonomy_target_for_step(step.phase, step.step)
            if self.config.taxonomy.include_in_planner_prompt
            else "Not provided."
        )

        prompt = f"""
You are a search-planning agent for biotech competitive intelligence.

STEP:
Phase: {step.phase}
Step: {step.step}
Activities: {step.activities}

CONTROLLED TAXONOMY TARGET:
{taxonomy_target}

Task:
Generate {query_count} web search queries to find companies that build, market, or materially deploy AI, agentic, autonomous, machine-learning, NLP, generative-AI, or workflow-automation solutions relevant to this exact step.

Requirements:
- Use the Key activities text aggressively: mine operational terms, acronyms, standards, systems, deliverables, workflows, and compliance phrases from it.
- Include incumbent enterprise platforms as well as AI-native startups.
- Include BPO, CRO, and systems-integrator offerings only when they have productized AI/automation capability for the step.
- Include one query using "agentic AI" or "AI agent" language.
- Include one query using broader "AI platform", "automation", "machine learning", or "NLP" language.
- Include one query aimed at vendor/platform discovery.
- Include one query aimed at product pages or solution pages.
- Focus on biotech / pharma / drug discovery / clinical / regulatory / safety / manufacturing relevance as appropriate.
- Do not drift outside the controlled taxonomy target.

Return JSON:
{{
  "queries": ["...", "...", "..."]
}}
"""
        try:
            data = self.llm.ask_json(prompt)
            return [query.strip() for query in data.get("queries", []) if query.strip()]
        except Exception:
            return []