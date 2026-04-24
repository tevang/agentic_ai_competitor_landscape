"""Agent that converts user-supplied companies into structured research requests."""

from lib.config import AppConfig
from lib.models import Candidate, CompanyResearchRequest, PipelineStep, UserSeedCompany
from lib.utils.text_utils import domain_from_url, unique_preserve_order


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
        )

    def build_step_seed_candidates(
        self,
        step: PipelineStep,
        seed_requests: list[CompanyResearchRequest],
    ) -> list[Candidate]:
        """Create seed candidates for a pipeline step using optional phase/step hints from the user."""

        candidates: list[Candidate] = []
        for request in seed_requests:
            phase_matches = not request.phase or request.phase.strip().lower() == step.phase.strip().lower()
            step_matches = not request.step or request.step.strip().lower() == step.step.strip().lower()

            if phase_matches and step_matches and (request.phase or request.step):
                confidence = 0.9 if request.phase and request.step else 0.78
                candidates.append(
                    Candidate(
                        name=request.company_name,
                        rationale="User-provided company candidate aligned with the supplied phase/step hint.",
                        vertical_or_horizontal_guess=request.classification or "unclear",
                        confidence=confidence,
                        evidence_urls=[request.website] if request.website else [],
                        source="user_seed",
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
    ) -> list[str]:
        """Construct company-enrichment search queries from user input and configured database domains."""

        queries = [
            f'"{company_name}" biotech AI company',
            f'"{company_name}" product platform biotech AI',
            f'"{company_name}" funding employees founded headquarters',
        ]

        if classification:
            queries.append(f'"{company_name}" {classification} biotech AI')

        if website:
            queries.append(f'"{company_name}" official website')

        if notes:
            queries.append(f'"{company_name}" {notes}')

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