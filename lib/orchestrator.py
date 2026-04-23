"""Top-level orchestration logic for the multi-agent competitive-intelligence workflow."""

import pandas as pd

from lib.agents.enrichment_agent import EnrichmentAgent
from lib.agents.extraction_agent import ExtractionAgent
from lib.agents.planner_agent import PlannerAgent
from lib.agents.presentation_agent import PresentationAgent
from lib.agents.research_agent import ResearchAgent
from lib.agents.verification_agent import VerificationAgent
from lib.analytics.scoring import build_matrix_df, build_profile_df, compute_gap_scores
from lib.config import AppConfig
from lib.models import CompanyProfile, PipelineStep
from lib.utils.text_utils import canonical_name


class CompetitiveLandscapeOrchestrator:
    """Run the end-to-end multi-agent workflow over the pipeline ontology."""

    def __init__(
        self,
        config: AppConfig,
        planner_agent: PlannerAgent,
        research_agent: ResearchAgent,
        extraction_agent: ExtractionAgent,
        enrichment_agent: EnrichmentAgent,
        verification_agent: VerificationAgent,
        presentation_agent: PresentationAgent,
    ) -> None:
        """Store the collaborating agents and global runtime configuration."""

        self.config = config
        self.planner_agent = planner_agent
        self.research_agent = research_agent
        self.extraction_agent = extraction_agent
        self.enrichment_agent = enrichment_agent
        self.verification_agent = verification_agent
        self.presentation_agent = presentation_agent

    def run(self, steps: list[PipelineStep]) -> dict[str, object]:
        """Execute the full workflow and return all structured and narrative outputs."""

        run_steps = steps[: self.config.runtime.max_steps] if self.config.runtime.max_steps > 0 else steps
        profile_cache: dict[str, CompanyProfile] = {}
        all_records: list[dict[str, object]] = []

        for step in run_steps:
            step_records, profile_cache = self.process_step(step, profile_cache)
            all_records.extend(step_records)

        records_df = pd.DataFrame(all_records)
        profile_df = build_profile_df(profile_cache)
        matrix_df = build_matrix_df(records_df)
        gap_df = compute_gap_scores(records_df, run_steps, self.config)
        gap_memo = self.presentation_agent.generate_gap_memo(matrix_df, profile_df, gap_df)
        slide_outline = self.presentation_agent.generate_slide_outline(matrix_df, profile_df, gap_df)

        return {
            "run_steps": run_steps,
            "records_df": records_df,
            "profile_df": profile_df,
            "matrix_df": matrix_df,
            "gap_df": gap_df,
            "gap_memo": gap_memo,
            "slide_outline": slide_outline,
        }

    def process_step(
        self,
        step: PipelineStep,
        profile_cache: dict[str, CompanyProfile],
    ) -> tuple[list[dict[str, object]], dict[str, CompanyProfile]]:
        """Process one pipeline step from query planning through verification."""

        if self.config.runtime.verbose:
            print(f"\n=== Processing: {step.phase} -> {step.step} ===")

        queries = self.planner_agent.build_query_plan(step)
        docs = self.research_agent.collect_step_evidence(step, queries)
        candidates = self.extraction_agent.extract_candidates(step, docs)

        if self.config.react.enable_refinement_pass and len(candidates) < self.config.react.min_candidates_before_refine:
            refined_queries = self.planner_agent.refine_queries(step, candidates)
            more_docs = self.research_agent.collect_step_evidence(step, refined_queries)
            docs.extend(more_docs)
            candidates = self.extraction_agent.extract_candidates(step, docs)

        records: list[dict[str, object]] = []
        for candidate in candidates[: self.config.runtime.max_candidates_per_step]:
            cache_key = canonical_name(candidate.name)

            if cache_key not in profile_cache:
                try:
                    profile_cache[cache_key] = self.enrichment_agent.enrich_company(candidate.name)
                except Exception as exc:
                    if self.config.runtime.verbose:
                        print(f"  [warn] enrichment failed for {candidate.name}: {exc}")
                    continue

            profile = profile_cache[cache_key]

            try:
                verdict = self.verification_agent.verify_company_for_step(step, profile, candidate.rationale)
            except Exception as exc:
                if self.config.runtime.verbose:
                    print(f"  [warn] verification failed for {profile.name}: {exc}")
                continue

            if verdict.include:
                records.append(
                    {
                        "phase": step.phase,
                        "step": step.step,
                        "company": profile.name,
                        "vertical_or_horizontal": profile.vertical_or_horizontal,
                        "funding": profile.funding,
                        "employees": profile.employees,
                        "founded": profile.founded,
                        "headquarters": profile.headquarters,
                        "presence": "; ".join(profile.presence),
                        "specialization": profile.specialization,
                        "agentic_posture": profile.explicit_agentic_posture,
                        "confidence": round(min(candidate.confidence, profile.confidence, verdict.confidence), 2),
                        "reason": verdict.reason,
                    }
                )

        if self.config.runtime.verbose:
            print(f"  kept {len(records)} verified companies")

        return records, profile_cache