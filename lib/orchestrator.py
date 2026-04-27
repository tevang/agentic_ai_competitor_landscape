"""Top-level orchestration logic for the multi-agent competitive-intelligence workflow."""

from pathlib import Path

import pandas as pd

from lib.agents.critical_agent import CriticalAgent
from lib.agents.enrichment_agent import EnrichmentAgent
from lib.agents.extraction_agent import ExtractionAgent
from lib.agents.fact_driven_analyst_agent import FactDrivenAnalystAgent
from lib.agents.planner_agent import PlannerAgent
from lib.agents.presentation_agent import PresentationAgent
from lib.agents.research_agent import ResearchAgent
from lib.agents.summary_agent import SummaryAgent
from lib.agents.taxonomy_enforcement_agent import TaxonomyEnforcementAgent
from lib.agents.user_company_intake_agent import UserCompanyIntakeAgent
from lib.agents.verification_agent import VerificationAgent
from lib.analytics.scoring import build_matrix_df, build_profile_df, compute_gap_scores
from lib.config import AppConfig
from lib.discovery.query_factory import build_step_search_terms
from lib.models import Candidate, CompanyProfile, CompanyResearchRequest, PipelineStep, UserSeedCompany
from lib.utils.logo_downloader import LogoDownloader
from lib.utils.report_writer import ReportWriter
from lib.utils.text_utils import canonical_name, unique_preserve_order


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
        summary_agent: SummaryAgent,
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
        self.summary_agent = summary_agent
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

        if self.config.runtime.process_user_seed_companies_first and self.config.runtime.analysis_mode == "deep_dive":
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

        records_df = pd.DataFrame(all_records)
        report_profile_cache = self._select_report_profile_cache(profile_cache, all_records)

        run_context = self.report_writer.prepare_run_directory()
        logo_paths = self.logo_downloader.download_logos(
            profiles=list(report_profile_cache.values()),
            logos_dir=run_context["logos_dir"],
        )
        for cache_key, logo_path in logo_paths.items():
            if cache_key in profile_cache:
                profile_cache[cache_key].logo_path = logo_path
            if cache_key in report_profile_cache:
                report_profile_cache[cache_key].logo_path = logo_path

        minimal_profiles = self.config.runtime.analysis_mode == "landscape_scan"
        profile_df = build_profile_df(report_profile_cache, minimal=minimal_profiles)
        matrix_df = build_matrix_df(records_df)
        gap_df = compute_gap_scores(records_df, run_steps, self.config)

        if self._should_generate_narratives():
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
        else:
            fact_analysis = self._build_scan_summary(matrix_df, profile_df, gap_df)
            critical_review = ""
            gap_memo = ""
            slide_outline = ""

        summary_df = pd.DataFrame(columns=self.config.summary.output_columns)
        summary_csv_path = ""
        if self.config.summary.enabled:
            summary_df, summary_csv_path = self.summary_agent.summarize_pipeline_results(
                matrix_df=matrix_df,
                profile_df=profile_df,
                gap_df=gap_df,
                fact_analysis=fact_analysis,
                critical_review=critical_review,
                gap_memo=gap_memo,
                slide_outline=slide_outline,
                run_dir=Path(run_context["run_dir"]),
            )

        results: dict[str, object] = {
            "run_steps": run_steps,
            "seed_requests": seed_requests,
            "records_df": records_df,
            "profile_df": profile_df,
            "matrix_df": matrix_df,
            "gap_df": gap_df,
            "summary_df": summary_df,
            "summary_csv_path": summary_csv_path,
            "fact_analysis": fact_analysis,
            "critical_review": critical_review,
            "gap_memo": gap_memo,
            "slide_outline": slide_outline,
            "run_context": run_context,
        }

        report_paths = self.report_writer.write_reports(results, run_context)
        if summary_csv_path:
            report_paths["summary_csv"] = summary_csv_path

        results["report_paths"] = report_paths
        return results

    def process_step(
        self,
        step: PipelineStep,
        profile_cache: dict[str, CompanyProfile],
        seed_request_map: dict[str, CompanyResearchRequest],
        step_seed_candidates: list[Candidate],
    ) -> tuple[list[dict[str, object]], dict[str, CompanyProfile]]:
        """Process one pipeline step from query planning through verification or cheap scan inclusion."""

        if self.config.runtime.verbose:
            print(f"\n=== Processing: {step.phase} -> {step.step} ===")

        step_taxonomy = self.taxonomy_enforcement_agent.map_step(step)
        step_terms = build_step_search_terms(
            step,
            max_terms=self.config.discovery.max_search_terms_per_step,
        )

        queries = self.planner_agent.build_query_plan(step)
        docs = self.research_agent.collect_step_evidence(step, queries)
        candidates = self.extraction_agent.extract_candidates(step, docs, seed_candidates=step_seed_candidates)

        if self.config.react.enable_refinement_pass and len(candidates) < self.config.react.min_candidates_before_refine:
            refined_queries = self.planner_agent.refine_queries(step, candidates)
            more_docs = self.research_agent.collect_step_evidence(step, refined_queries)
            docs.extend(more_docs)
            candidates = self.extraction_agent.extract_candidates(step, docs, seed_candidates=step_seed_candidates)

        if self.config.runtime.analysis_mode == "landscape_scan":
            records = self._process_landscape_scan_candidates(
                step=step,
                candidates=candidates,
                profile_cache=profile_cache,
                step_taxonomy=step_taxonomy,
            )
            if self.config.runtime.verbose:
                print(f"  kept {len(records)} first-pass candidate companies")
            return records, profile_cache

        records: list[dict[str, object]] = []
        for candidate in candidates[: self.config.runtime.max_candidates_per_step]:
            if (candidate.evidence_role or "").strip().lower() == "publisher_only":
                if self.config.runtime.verbose:
                    print(f"  [skip] publisher-only source, not vendor: {candidate.name}")
                continue

            candidate_company_name = candidate.owning_company_name or candidate.name
            cache_key = canonical_name(candidate_company_name)

            research_request = seed_request_map.get(cache_key) or self.user_company_intake_agent.build_default_request(
                company_name=candidate_company_name,
                classification=candidate.vertical_or_horizontal_guess,
                phase=step.phase,
                step=step.step,
                activities=step.activities,
                step_terms=step_terms,
                product_or_solution=candidate.product_or_solution,
                candidate_rationale=candidate.rationale,
                candidate_evidence_urls=candidate.evidence_urls,
            )

            if cache_key not in profile_cache:
                try:
                    profile = self.enrichment_agent.enrich_company(research_request)
                    self._store_profile_aliases(profile_cache, cache_key, profile)
                except Exception as exc:
                    if self.config.runtime.verbose:
                        print(f"  [warn] enrichment failed for {candidate_company_name}: {exc}")
                    continue

            profile = profile_cache[cache_key]

            if candidate.product_or_solution:
                profile.products_or_solutions = unique_preserve_order(
                    profile.products_or_solutions + [candidate.product_or_solution]
                )

            try:
                verdict = self.verification_agent.verify_company_for_step(
                    step=step,
                    profile=profile,
                    candidate_rationale=candidate.rationale,
                    taxonomy_assignment=step_taxonomy,
                    candidate_evidence_urls=candidate.evidence_urls,
                    candidate_product_or_solution=candidate.product_or_solution,
                )
            except Exception as exc:
                if self.config.runtime.verbose:
                    print(f"  [warn] verification failed for {profile.name}: {exc}")
                continue

            if verdict.include:
                profile = self.taxonomy_enforcement_agent.apply_step_taxonomy(profile, step_taxonomy)
                self._store_profile_aliases(profile_cache, cache_key, profile)

                product_or_solution = candidate.product_or_solution or self._first_product(profile)
                competitor_label = self._competitor_label(profile.name, product_or_solution)

                records.append(
                    self._build_record(
                        step=step,
                        profile=profile,
                        product_or_solution=product_or_solution,
                        competitor_label=competitor_label,
                        confidence=round(min(candidate.confidence, profile.confidence, verdict.confidence), 2),
                        reason=verdict.reason,
                        verification_mode="deep_dive_verified",
                    )
                )

        if self.config.runtime.verbose:
            print(f"  kept {len(records)} verified companies")

        return records, profile_cache

    def _process_landscape_scan_candidates(
        self,
        step: PipelineStep,
        candidates: list[Candidate],
        profile_cache: dict[str, CompanyProfile],
        step_taxonomy,
    ) -> list[dict[str, object]]:
        """Convert extraction candidates into minimal first-pass profiles without enrichment/verification."""

        records: list[dict[str, object]] = []
        allowed_postures = {
            value.strip().lower()
            for value in self.config.discovery.landscape_scan_agentic_postures
            if value.strip()
        }

        for candidate in candidates[: self.config.runtime.max_candidates_per_step]:
            if (candidate.evidence_role or "").strip().lower() == "publisher_only":
                if self.config.runtime.verbose:
                    print(f"  [scan-skip] publisher-only source, not vendor: {candidate.name}")
                continue

            posture = (candidate.explicit_agentic_posture or "unclear").strip().lower()
            if allowed_postures and posture not in allowed_postures:
                if self.config.runtime.verbosity >= 1:
                    print(f"  [scan-skip] posture={posture}: {candidate.name}")
                continue

            company_name = candidate.owning_company_name or candidate.name
            cache_key = canonical_name(company_name)
            profile = self._minimal_profile_from_candidate(candidate, step_taxonomy)
            profile = self.taxonomy_enforcement_agent.apply_step_taxonomy(profile, step_taxonomy)
            self._store_profile_aliases(profile_cache, cache_key, profile)

            product_or_solution = candidate.product_or_solution or self._first_product(profile)
            competitor_label = self._competitor_label(profile.name, product_or_solution)

            records.append(
                self._build_record(
                    step=step,
                    profile=profile,
                    product_or_solution=product_or_solution,
                    competitor_label=competitor_label,
                    confidence=round(min(candidate.confidence, profile.confidence), 2),
                    reason=candidate.rationale,
                    verification_mode="landscape_scan_unverified",
                )
            )

        return records

    def _minimal_profile_from_candidate(self, candidate: Candidate, step_taxonomy) -> CompanyProfile:
        """Create a minimal first-pass company profile from a candidate."""

        company_name = candidate.owning_company_name or candidate.name
        product = candidate.product_or_solution.strip()
        website = candidate.website.strip()
        posture = candidate.explicit_agentic_posture.strip().lower() or "unclear"

        return CompanyProfile(
            name=company_name,
            vertical_or_horizontal=candidate.vertical_or_horizontal_guess or "unknown",
            website=website,
            specialization=candidate.rationale,
            explicit_agentic_posture=posture,
            confidence=candidate.confidence,
            evidence_urls=unique_preserve_order(candidate.evidence_urls),
            taxonomy_primary_phase=step_taxonomy.primary_phase,
            taxonomy_primary_subcategory=step_taxonomy.primary_subcategory,
            taxonomy_phase_labels=list(step_taxonomy.phase_labels),
            taxonomy_subcategory_labels=list(step_taxonomy.subcategory_labels),
            products_or_solutions=[product] if product else [],
        )

    def _build_record(
        self,
        step: PipelineStep,
        profile: CompanyProfile,
        product_or_solution: str,
        competitor_label: str,
        confidence: float,
        reason: str,
        verification_mode: str,
    ) -> dict[str, object]:
        """Build a normalized record row for matrix/profile/gap analytics."""

        return {
            "phase": step.phase,
            "step": step.step,
            "company": profile.name,
            "competitor_label": competitor_label,
            "product_or_solution": product_or_solution,
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
            "taxonomy_primary_phase": profile.taxonomy_primary_phase,
            "taxonomy_primary_subcategory": profile.taxonomy_primary_subcategory,
            "confidence": confidence,
            "reason": reason,
            "verification_mode": verification_mode,
        }

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
                profile = self.enrichment_agent.enrich_company(request)
                self._store_profile_aliases(profile_cache, cache_key, profile)
            except Exception as exc:
                if self.config.runtime.verbose:
                    print(f"  [warn] seed-company enrichment failed for {request.company_name}: {exc}")

        return profile_cache

    def _select_report_profile_cache(
        self,
        profile_cache: dict[str, CompanyProfile],
        records: list[dict[str, object]],
    ) -> dict[str, CompanyProfile]:
        """Return profiles that should appear in the report, deduped by enriched company name."""

        deduped_all = self._dedupe_profiles_by_name(profile_cache)

        if self.config.reporting.include_unverified_profiles:
            return deduped_all

        included_keys = {
            canonical_name(str(record.get("company", "")))
            for record in records
            if record.get("company")
        }

        selected: dict[str, CompanyProfile] = {}
        for profile_key, profile in deduped_all.items():
            if profile_key in included_keys:
                selected[profile_key] = profile

        return selected

    def _store_profile_aliases(
        self,
        profile_cache: dict[str, CompanyProfile],
        candidate_key: str,
        profile: CompanyProfile,
    ) -> None:
        """Store a profile under both the candidate key and enriched company-name key."""

        profile_key = canonical_name(profile.name)
        profile_cache[candidate_key] = profile
        profile_cache[profile_key] = profile

    def _dedupe_profiles_by_name(
        self,
        profile_cache: dict[str, CompanyProfile],
    ) -> dict[str, CompanyProfile]:
        """Deduplicate alias-keyed profile cache by enriched company name."""

        deduped: dict[str, CompanyProfile] = {}
        for profile in profile_cache.values():
            profile_key = canonical_name(profile.name)
            if profile_key not in deduped:
                deduped[profile_key] = profile
                continue

            existing = deduped[profile_key]
            existing.products_or_solutions = unique_preserve_order(
                existing.products_or_solutions + profile.products_or_solutions
            )
            existing.evidence_urls = unique_preserve_order(existing.evidence_urls + profile.evidence_urls)
            if profile.confidence > existing.confidence:
                deduped[profile_key] = profile

        return deduped

    def _should_generate_narratives(self) -> bool:
        """Return whether expensive narrative agents should run."""

        if self.config.runtime.analysis_mode == "landscape_scan":
            return self.config.reporting.generate_narratives_in_landscape_scan
        return True

    def _build_scan_summary(
        self,
        matrix_df: pd.DataFrame,
        profile_df: pd.DataFrame,
        gap_df: pd.DataFrame,
    ) -> str:
        """Build a deterministic first-pass summary without LLM calls."""

        competitor_count = int(profile_df["company"].nunique()) if not profile_df.empty else 0
        step_count = int(matrix_df[["phase", "step"]].drop_duplicates().shape[0]) if not matrix_df.empty else 0
        explicit_count = int((profile_df["agentic_posture"] == "explicit").sum()) if not profile_df.empty else 0
        adjacent_count = int((profile_df["agentic_posture"] == "adjacent").sum()) if not profile_df.empty else 0

        return (
            "Landscape scan mode completed. "
            f"Mapped {competitor_count} candidate companies across {step_count} step(s). "
            f"Agentic posture labels: explicit={explicit_count}, adjacent={adjacent_count}. "
            "This first-pass map intentionally skips deep enrichment, per-company verification, "
            "funding/headcount/founded/HQ extraction, and narrative analysis to reduce Tavily and OpenAI usage. "
            "Run analysis_mode=deep_dive with deep_dive_subphases populated to enrich and verify selected subphases."
        )

    def _first_product(self, profile: CompanyProfile) -> str:
        """Return the first known product/solution for a profile."""

        return profile.products_or_solutions[0] if profile.products_or_solutions else ""

    def _competitor_label(self, company_name: str, product_or_solution: str) -> str:
        """Build a display label that preserves product context without losing company ownership."""

        if not product_or_solution:
            return company_name

        normalized_company = canonical_name(company_name)
        normalized_product = canonical_name(product_or_solution)
        if normalized_company and normalized_company in normalized_product:
            return product_or_solution

        return f"{company_name} ({product_or_solution})"