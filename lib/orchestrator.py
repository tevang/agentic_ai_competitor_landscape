"""Top-level orchestration logic for the multi-agent competitive-intelligence workflow."""

import pandas as pd

from lib.agents.critical_agent import CriticalAgent
from lib.agents.enrichment_agent import EnrichmentAgent
from lib.agents.extraction_agent import ExtractionAgent
from lib.agents.fact_driven_analyst_agent import FactDrivenAnalystAgent
from lib.agents.planner_agent import PlannerAgent
from lib.agents.presentation_agent import PresentationAgent
from lib.agents.research_agent import ResearchAgent
from lib.agents.taxonomy_enforcement_agent import TaxonomyEnforcementAgent
from lib.agents.user_company_intake_agent import UserCompanyIntakeAgent
from lib.agents.verification_agent import VerificationAgent
from lib.analytics.scoring import build_matrix_df, build_profile_df, compute_gap_scores
from lib.config import AppConfig
from lib.models import Candidate, CompanyProfile, CompanyResearchRequest, PipelineStep, UserSeedCompany
from lib.utils.logo_downloader import LogoDownloader
from lib.utils.report_writer import ReportWriter
from lib.utils.text_utils import canonical_name


class CompetitiveLandscapeOrchestrator:
    """Run the end-to-end multi-agent workflow over the pipeline ontology."""

    def __init__(
        self,
        config: AppConfig,
        planner_agent: PlannerAgent,
        research_agent: ResearchAgent,
        extraction_agent: ExtractionAgent,
        taxonomy_enforcement_agent: TaxonomyEnforcementAgent,
        enrichment_agent: EnrichmentAgent,
        verification_agent: VerificationAgent,
        presentation_agent: PresentationAgent,
        user_company_intake_agent: UserCompanyIntakeAgent,
        fact_driven_analyst_agent: FactDrivenAnalystAgent,
        critical_agent: CriticalAgent,
        report_writer: ReportWriter,
        logo_downloader: LogoDownloader,
    ) -> None:
        """Store the collaborating agents, report writer, and runtime configuration."""

        self.config = config
        self.planner_agent = planner_agent
        self.research_agent = research_agent
        self.extraction_agent = extraction_agent
        self.taxonomy_enforcement_agent = taxonomy_enforcement_agent
        self.enrichment_agent = enrichment_agent
        self.verification_agent = verification_agent
        self.presentation_agent = presentation_agent
        self.user_company_intake_agent = user_company_intake_agent
        self.fact_driven_analyst_agent = fact_driven_analyst_agent
        self.critical_agent = critical_agent
        self.report_writer = report_writer
        self.logo_downloader = logo_downloader

    def run(
        self,
        steps: list[PipelineStep],
        seed_companies: list[UserSeedCompany] | None = None,
    ) -> dict[str, object]:
        """Execute the full workflow and return all structured and narrative outputs."""

        run_steps = steps[: self.config.runtime.max_steps] if self.config.runtime.max_steps > 0 else steps
        profile_cache: dict[str, CompanyProfile] = {}
        all_records: list[dict[str, object]] = []
        seed_companies = seed_companies or []

        seed_requests = self.user_company_intake_agent.prepare_seed_company_requests(seed_companies)
        seed_request_map = {
            canonical_name(request.company_name): request for request in seed_requests
        }

        if self.config.runtime.process_user_seed_companies_first:
            profile_cache = self._preload_seed_company_profiles(seed_requests, profile_cache)

        for step in run_steps:
            step_seed_candidates = (
                self.user_company_intake_agent.build_step_seed_candidates(step, seed_requests)
                if self.config.runtime.match_seed_companies_to_steps
                else []
            )
            step_records, profile_cache = self.process_step(
                step=step,
                profile_cache=profile_cache,
                seed_request_map=seed_request_map,
                step_seed_candidates=step_seed_candidates,
            )
            all_records.extend(step_records)

        run_context = self.report_writer.prepare_run_directory()
        logo_paths = self.logo_downloader.download_logos(
            profiles=list(profile_cache.values()),
            logos_dir=run_context["logos_dir"],
        )
        for cache_key, logo_path in logo_paths.items():
            if cache_key in profile_cache:
                profile_cache[cache_key].logo_path = logo_path

        records_df = pd.DataFrame(all_records)
        profile_df = build_profile_df(profile_cache)
        matrix_df = build_matrix_df(records_df)
        gap_df = compute_gap_scores(records_df, run_steps, self.config)

        fact_analysis = self.fact_driven_analyst_agent.analyze(matrix_df, profile_df, gap_df)
        critical_review = self.critical_agent.challenge(matrix_df, profile_df, gap_df, fact_analysis)
        gap_memo = self.presentation_agent.generate_gap_memo(
            matrix_df=matrix_df,
            profile_df=profile_df,
            gap_df=gap_df,
            fact_analysis=fact_analysis,
            critical_review=critical_review,
        )
        slide_outline = self.presentation_agent.generate_slide_outline(
            matrix_df=matrix_df,
            profile_df=profile_df,
            gap_df=gap_df,
            fact_analysis=fact_analysis,
            critical_review=critical_review,
        )

        results: dict[str, object] = {
            "run_steps": run_steps,
            "seed_requests": seed_requests,
            "records_df": records_df,
            "profile_df": profile_df,
            "matrix_df": matrix_df,
            "gap_df": gap_df,
            "fact_analysis": fact_analysis,
            "critical_review": critical_review,
            "gap_memo": gap_memo,
            "slide_outline": slide_outline,
            "run_context": run_context,
        }
        report_paths = self.report_writer.write_reports(results, run_context)
        results["report_paths"] = report_paths
        return results

    def process_step(
        self,
        step: PipelineStep,
        profile_cache: dict[str, CompanyProfile],
        seed_request_map: dict[str, CompanyResearchRequest],
        step_seed_candidates: list[Candidate],
    ) -> tuple[list[dict[str, object]], dict[str, CompanyProfile]]:
        """Process one pipeline step from query planning through verification."""

        if self.config.runtime.verbose:
            print(f"\n=== Processing: {step.phase} -> {step.step} ===")

        step_taxonomy = self.taxonomy_enforcement_agent.map_step(step)

        queries = self.planner_agent.build_query_plan(step)
        docs = self.research_agent.collect_step_evidence(step, queries)
        candidates = self.extraction_agent.extract_candidates(step, docs, seed_candidates=step_seed_candidates)

        if self.config.react.enable_refinement_pass and len(candidates) < self.config.react.min_candidates_before_refine:
            refined_queries = self.planner_agent.refine_queries(step, candidates)
            more_docs = self.research_agent.collect_step_evidence(step, refined_queries)
            docs.extend(more_docs)
            candidates = self.extraction_agent.extract_candidates(step, docs, seed_candidates=step_seed_candidates)

        records: list[dict[str, object]] = []
        for candidate in candidates[: self.config.runtime.max_candidates_per_step]:
            cache_key = canonical_name(candidate.name)
            research_request = seed_request_map.get(cache_key) or self.user_company_intake_agent.build_default_request(
                company_name=candidate.name,
                classification=candidate.vertical_or_horizontal_guess,
                phase=step.phase,
                step=step.step,
            )

            if cache_key not in profile_cache:
                try:
                    profile_cache[cache_key] = self.enrichment_agent.enrich_company(research_request)
                except Exception as exc:
                    if self.config.runtime.verbose:
                        print(f"  [warn] enrichment failed for {candidate.name}: {exc}")
                    continue

            profile = profile_cache[cache_key]

            try:
                verdict = self.verification_agent.verify_company_for_step(
                    step=step,
                    profile=profile,
                    candidate_rationale=candidate.rationale,
                    taxonomy_assignment=step_taxonomy,
                )
            except Exception as exc:
                if self.config.runtime.verbose:
                    print(f"  [warn] verification failed for {profile.name}: {exc}")
                continue

            if verdict.include:
                profile = self.taxonomy_enforcement_agent.apply_step_taxonomy(profile, step_taxonomy)
                profile_cache[cache_key] = profile

                records.append(
                    {
                        "phase": step.phase,
                        "step": step.step,
                        "company": profile.name,
                        "vertical_or_horizontal": profile.vertical_or_horizontal,
                        "funding": profile.funding,
                        "funding_rounds": profile.funding_rounds,
                        "employees": profile.employees,
                        "founded": profile.founded,
                        "headquarters": profile.headquarters,
                        "presence": "; ".join(profile.presence),
                        "website": profile.website,
                        "specialization": profile.specialization,
                        "agentic_posture": profile.explicit_agentic_posture,
                        "taxonomy_primary_phase": step_taxonomy.primary_phase,
                        "taxonomy_primary_subcategory": step_taxonomy.primary_subcategory,
                        "confidence": round(min(candidate.confidence, profile.confidence, verdict.confidence), 2),
                        "reason": verdict.reason,
                    }
                )

        if self.config.runtime.verbose:
            print(f"  kept {len(records)} verified companies")

        return records, profile_cache

    def _preload_seed_company_profiles(
        self,
        seed_requests: list[CompanyResearchRequest],
        profile_cache: dict[str, CompanyProfile],
    ) -> dict[str, CompanyProfile]:
        """Confirm and enrich user-provided seed companies before normal discovery starts."""

        for request in seed_requests:
            cache_key = canonical_name(request.company_name)
            if cache_key in profile_cache:
                continue

            try:
                if self.config.runtime.verbose:
                    print(f"\n=== Preloading seed company: {request.company_name} ===")
                profile_cache[cache_key] = self.enrichment_agent.enrich_company(request)
            except Exception as exc:
                if self.config.runtime.verbose:
                    print(f"  [warn] seed-company enrichment failed for {request.company_name}: {exc}")

        return profile_cache