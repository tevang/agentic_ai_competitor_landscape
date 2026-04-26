"""Agent that converts user-supplied companies into structured research requests."""

from lib.config import AppConfig
from lib.discovery.query_factory import build_step_search_terms
from lib.models import Candidate, CompanyResearchRequest, PipelineStep, UserSeedCompany
from lib.utils.text_utils import canonical_name, domain_from_url, unique_preserve_order


TRACKED_COMPANY_FIELDS = [
    "funding",
    "funding_rounds",
    "employees",
    "founded",
    "headquarters",
    "presence",
]


class UserCompanyIntakeAgent:
    """Transform user-supplied companies into normalized requests for the research agent."""

    def __init__(self, config: AppConfig) -> None:
        """Store the configuration required to build company research requests."""

        self.config = config

    def prepare_seed_company_requests(
        self,
        seed_companies: list[UserSeedCompany],
    ) -> list[CompanyResearchRequest]:
        """Convert user-supplied company rows into research requests."""

        return [self.prepare_seed_company_request(seed_company) for seed_company in seed_companies]

    def prepare_seed_company_request(self, seed_company: UserSeedCompany) -> CompanyResearchRequest:
        """Create a research request for one user-supplied company row."""

        known_fields = {
            "funding": seed_company.funding,
            "funding_rounds": seed_company.funding_rounds,
            "employees": seed_company.employees,
            "founded": seed_company.founded,
            "headquarters": seed_company.headquarters,
            "presence": seed_company.presence,
        }
        known_fields = {key: value for key, value in known_fields.items() if value}

        preferred_domains = []
        if seed_company.website:
            preferred_domains.append(domain_from_url(seed_company.website))

        for field_name in TRACKED_COMPANY_FIELDS:
            preferred_domains.extend(
                domain_from_url(url) for url in self.config.company_data_sources.urls_for_field(field_name)
            )

        query_hints = self._build_company_queries(
            company_name=seed_company.company_name,
            classification=seed_company.classification,
            website=seed_company.website,
            notes=seed_company.notes,
            preferred_domains=preferred_domains,
        )
        query_hints = query_hints[: self.config.get_active_search_profile().queries_per_company]

        return CompanyResearchRequest(
            company_name=seed_company.company_name,
            classification=seed_company.classification or "",
            website=seed_company.website or "",
            phase=seed_company.phase or "",
            step=seed_company.step or "",
            notes=seed_company.notes or "",
            known_fields=known_fields,
            preferred_domains=unique_preserve_order(preferred_domains),
            query_hints=unique_preserve_order(query_hints),
        )

    def build_default_request(
        self,
        company_name: str,
        classification: str = "",
        phase: str = "",
        step: str = "",
        activities: str = "",
        step_terms: list[str] | None = None,
        product_or_solution: str = "",
        candidate_rationale: str = "",
        candidate_evidence_urls: list[str] | None = None,
    ) -> CompanyResearchRequest:
        """Create a default company research request for a discovered candidate."""

        preferred_domains = []
        for field_name in TRACKED_COMPANY_FIELDS:
            preferred_domains.extend(
                domain_from_url(url) for url in self.config.company_data_sources.urls_for_field(field_name)
            )

        query_hints = self._build_company_queries(
            company_name=company_name,
            classification=classification,
            website="",
            notes="",
            preferred_domains=preferred_domains,
            phase=phase,
            step=step,
            activities=activities,
            step_terms=step_terms or [],
            product_or_solution=product_or_solution,
        )
        query_hints = query_hints[: self.config.get_active_search_profile().queries_per_company]

        return CompanyResearchRequest(
            company_name=company_name,
            classification=classification or "",
            website="",
            phase=phase,
            step=step,
            notes="",
            known_fields={},
            preferred_domains=unique_preserve_order(preferred_domains),
            query_hints=unique_preserve_order(query_hints),
            product_or_solution=product_or_solution,
            candidate_rationale=candidate_rationale,
            candidate_evidence_urls=unique_preserve_order(candidate_evidence_urls or []),
        )

    def build_step_seed_candidates(
        self,
        step: PipelineStep,
        seed_requests: list[CompanyResearchRequest],
    ) -> list[Candidate]:
        """Create seed candidates for a pipeline step using explicit hints or optional text overlap."""

        candidates: list[Candidate] = []
        for request in seed_requests:
            phase_matches = not request.phase or request.phase.strip().lower() == step.phase.strip().lower()
            step_matches = not request.step or request.step.strip().lower() == step.step.strip().lower()

            if phase_matches and step_matches and (request.phase or request.step):
                confidence = 0.9 if request.phase and request.step else 0.78
                candidates.append(
                    Candidate(
                        name=request.company_name,
                        owning_company_name=request.company_name,
                        product_or_solution=request.product_or_solution,
                        evidence_role="target_vendor",
                        rationale="User-provided company candidate aligned with the supplied phase/step hint.",
                        vertical_or_horizontal_guess=request.classification or "unclear",
                        confidence=confidence,
                        evidence_urls=[request.website] if request.website else [],
                        source="user_seed",
                    )
                )
                continue

            if (
                self.config.discovery.include_seed_companies_without_step_hints
                and not request.phase
                and not request.step
                and self._global_seed_text_matches_step(request, step)
            ):
                candidates.append(
                    Candidate(
                        name=request.company_name,
                        owning_company_name=request.company_name,
                        product_or_solution=request.product_or_solution,
                        evidence_role="target_vendor",
                        rationale="User-provided global seed candidate with text overlap against derived step terms.",
                        vertical_or_horizontal_guess=request.classification or "unclear",
                        confidence=0.55,
                        evidence_urls=[request.website] if request.website else [],
                        source="user_seed_global_overlap",
                    )
                )

        return candidates

    def _build_company_queries(
        self,
        company_name: str,
        classification: str,
        website: str,
        notes: str,
        preferred_domains: list[str],
        phase: str = "",
        step: str = "",
        activities: str = "",
        step_terms: list[str] | None = None,
        product_or_solution: str = "",
    ) -> list[str]:
        """Construct company-enrichment queries from user input, product context, step terms, and priority domains."""

        del activities  # Accepted for future extension without changing call sites.

        queries: list[str] = []

        if product_or_solution:
            queries.extend(
                [
                    f'"{company_name}" "{product_or_solution}"',
                    f'"{product_or_solution}" "{step}" AI automation',
                    f'"{product_or_solution}" pharmacovigilance AI agents',
                    f'"{product_or_solution}" case intake case processing',
                    f'"{product_or_solution}" official product page',
                ]
            )

        queries.extend(
            [
            f'"{company_name}" official website',
            f'"{company_name}" product platform biotech AI',
            f'"{company_name}" life sciences AI software',
            f'"{company_name}" funding employees founded headquarters',
        ]
        )

        if classification:
            queries.append(f'"{company_name}" {classification} biotech AI')

        if website:
            queries.append(f'"{company_name}" official website')

        if notes:
            queries.append(f'"{company_name}" {notes}')

        if step:
            queries.extend(
                [
                    f'"{company_name}" "{step}" AI automation',
                    f'"{company_name}" "{step}" software platform',
                    f'"{company_name}" "{step}" "life sciences"',
                ]
            )

        if phase:
            queries.append(f'"{company_name}" "{phase}" AI platform')

        if self.config.discovery.company_evidence_include_step_terms:
            for term in (step_terms or [])[:10]:
                queries.append(f'"{company_name}" "{term}"')
                queries.append(f'"{company_name}" "{term}" AI automation')
                if product_or_solution:
                    queries.append(f'"{product_or_solution}" "{term}"')

        field_query_terms = {
            "funding": "funding",
            "funding_rounds": "funding rounds",
            "employees": "employee count",
            "founded": "founded year",
            "headquarters": "headquarters",
            "presence": "offices locations",
        }
        for field_name, search_term in field_query_terms.items():
            for domain in preferred_domains:
                queries.append(f'site:{domain} "{company_name}" {search_term}')

        return unique_preserve_order(queries)

    def _global_seed_text_matches_step(self, request: CompanyResearchRequest, step: PipelineStep) -> bool:
        """Check whether a generic seed company plausibly overlaps the active step."""

        terms = build_step_search_terms(step, max_terms=self.config.discovery.max_search_terms_per_step)
        seed_text_parts = [
            request.company_name,
            request.classification,
            request.website,
            request.notes,
            request.product_or_solution,
            " ".join(request.known_fields.values()),
            " ".join(request.query_hints),
        ]
        seed_text = canonical_name(" ".join(seed_text_parts))

        overlap = 0
        for term in terms:
            key = canonical_name(term)
            if len(key) >= 4 and key in seed_text:
                overlap += 1

        return overlap >= self.config.discovery.global_seed_step_match_min_token_overlap