"""Enrichment agent that builds normalized company profiles from evidence."""

import json

from lib.agents.research_agent import ResearchAgent
from lib.config import AppConfig
from lib.llm import LLM
from lib.models import CompanyProfile, CompanyResearchRequest, EvidenceDoc
from lib.retrieval.evidence_store import EvidenceStore
from lib.utils.text_utils import evidence_to_context, parse_delimited_list, unique_preserve_order


class EnrichmentAgent:
    """Enrich company candidates with profile-level metadata and positioning."""

    def __init__(
        self,
        llm: LLM,
        config: AppConfig,
        research_agent: ResearchAgent,
        store: EvidenceStore,
    ) -> None:
        """Store the services needed to enrich and cache a company profile."""

        self.llm = llm
        self.config = config
        self.research_agent = research_agent
        self.store = store

    def enrich_company(self, request: CompanyResearchRequest) -> CompanyProfile:
        """Collect evidence for a company request and convert it into a normalized profile."""

        cached_profile = None
        if self.config.search_protocol.reuse_existing_profiles:
            cached_profile = self.store.get_company_profile(
                company_name=request.company_name,
                min_confidence=self.config.search_protocol.skip_llm_if_existing_profile_confidence_at_least,
            )
            if cached_profile is not None and self._cached_profile_is_usable(cached_profile):
                return self._merge_profile_with_request(cached_profile, request)

        docs = self.research_agent.collect_company_evidence(request)
        rag_docs = self.store.query(
            text=f"{request.company_name} company funding funding rounds employees founded headquarters offices specialization",
            n_results=self.config.rag.enrichment_rag_results,
        )

        context_items = docs + [
            EvidenceDoc(
                phase="RAG",
                step="RAG",
                query=document.get("query", ""),
                url=document.get("url", ""),
                title=document.get("title", ""),
                snippet=document.get("snippet", ""),
                text=document.get("text", ""),
                company_name=request.company_name,
                source_type="rag_retrieval",
            )
            for document in rag_docs
        ]
        context = evidence_to_context(
            context_items,
            limit=self.config.rag.enrichment_context_limit,
            chars_per_item=self.config.rag.enrichment_context_chars_per_item,
        )

        prompt = f"""
You are a company enrichment agent.

COMPANY:
{request.company_name}

Definitions:
- vertical = built specifically for drug R&D / pharma / life-sciences workflows
- horizontal = broader scientific-agent, lab-automation, or research platform spanning multiple domains

Rules:
- Prefer "unknown" to guessing.
- Confirm or correct the user-provided information if evidence contradicts it.
- Funding can be a round amount or total disclosed funding.
- Funding rounds can be an integer count or a public description such as "unknown".
- Employees can be an official count or a public range like "201-500".
- Presence should list offices, operating hubs, or notable geographic footprint.
- Website should be the official company website when available.
- Logo path must remain blank. It will be filled later by the logo downloader.

USER-PROVIDED INPUT TO CONFIRM:
{json.dumps(request.known_fields, indent=2, ensure_ascii=False)}

USER CLASSIFICATION HINT:
{request.classification or "unknown"}

USER WEBSITE HINT:
{request.website or "unknown"}

PREFERRED DOMAINS:
{json.dumps(request.preferred_domains, indent=2, ensure_ascii=False)}

EVIDENCE:
{context}

Return JSON:
{{
  "name": "{request.company_name}",
  "vertical_or_horizontal": "vertical|horizontal|unknown",
  "funding": "string",
  "funding_rounds": "string",
  "employees": "string",
  "founded": "string",
  "headquarters": "string",
  "presence": ["string"],
  "website": "string",
  "specialization": "short description",
  "explicit_agentic_posture": "explicit|adjacent|unclear",
  "confidence": 0.0,
  "evidence_urls": ["url1", "url2"],
  "logo_path": ""
}}
"""
        data = self.llm.ask_json(prompt)
        profile = CompanyProfile(**data)
        merged_profile = self._merge_profile_with_request(profile, request)
        merged_profile.evidence_urls = unique_preserve_order(merged_profile.evidence_urls)
        self.store.save_company_profile(merged_profile)
        return merged_profile

    def _cached_profile_is_usable(self, profile: CompanyProfile) -> bool:
        """Decide whether a cached profile is complete enough to skip a fresh LLM call."""

        fields = [
            profile.vertical_or_horizontal,
            profile.funding,
            profile.funding_rounds,
            profile.employees,
            profile.founded,
            profile.headquarters,
            profile.website,
            profile.specialization,
        ]
        missing_count = sum(1 for value in fields if not value or str(value).strip().lower() == "unknown")
        return missing_count <= 2

    def _merge_profile_with_request(
        self,
        profile: CompanyProfile,
        request: CompanyResearchRequest,
    ) -> CompanyProfile:
        """Merge trusted user-provided hints into blank fields of the enriched profile."""

        if request.classification and profile.vertical_or_horizontal in {"", "unknown"}:
            profile.vertical_or_horizontal = request.classification

        if request.website and not profile.website:
            profile.website = request.website

        for field_name, value in request.known_fields.items():
            if not value:
                continue

            if field_name == "presence":
                if not profile.presence:
                    profile.presence = parse_delimited_list(value)
                continue

            if hasattr(profile, field_name) and not getattr(profile, field_name):
                setattr(profile, field_name, value)

        return profile