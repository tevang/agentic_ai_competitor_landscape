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
            if cached_profile is not None and self._cached_profile_is_usable(cached_profile, request):
                return self._merge_profile_with_request(cached_profile, request)

        docs = self.research_agent.collect_company_evidence(request)
        rag_docs = self.store.query(
            text=(
                f"{request.company_name} {request.product_or_solution} "
                f"{request.phase} {request.step} company funding employees founded headquarters "
                f"AI automation agentic product platform pharmacovigilance safety"
            ),
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

PRODUCT / SOLUTION CONTEXT:
{request.product_or_solution or "unknown"}

PIPELINE CONTEXT:
Phase: {request.phase or "unknown"}
Step: {request.step or "unknown"}

CANDIDATE RATIONALE FROM EXTRACTION:
{request.candidate_rationale or "unknown"}

Definitions:
- vertical = built specifically for drug R&D / pharma / life-sciences workflows
- horizontal = broader scientific-agent, lab-automation, AI, infrastructure, or research platform spanning multiple domains
- explicit_agentic_posture = "explicit" when evidence mentions AI agents, agentic AI, autonomous workflows, copilots, LLM/GenAI agents, or a clearly autonomous/agent-like product posture
- explicit_agentic_posture = "adjacent" when evidence shows AI, ML, NLP, cognitive automation, or productized workflow automation but not explicitly agentic/autonomous
- explicit_agentic_posture = "unclear" when the evidence does not support AI/automation claims

Rules:
- Prefer "unknown" to guessing.
- Preserve product context. If a candidate is a product line such as Vault Safety, Argus Safety, LifeSphere Safety, SafetyEasy, HALOPV, or OnePV, return the owning company in "name" and list the product in "products_or_solutions".
- Do not turn article publishers, analysts, blogs, or implementation partners into the company profile unless they themselves sell the relevant product/platform.
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
  "specialization": "short description emphasizing the relevant product/solution and pipeline step",
  "explicit_agentic_posture": "explicit|adjacent|unclear",
  "confidence": 0.0,
  "evidence_urls": ["url1", "url2"],
  "logo_path": "",
  "products_or_solutions": ["product or solution name"]
}}
"""
        data = self.llm.ask_json(prompt)
        profile = CompanyProfile(**data)
        merged_profile = self._merge_profile_with_request(profile, request)
        merged_profile.evidence_urls = unique_preserve_order(merged_profile.evidence_urls)
        merged_profile.products_or_solutions = unique_preserve_order(merged_profile.products_or_solutions)
        self.store.save_company_profile(merged_profile)
        return merged_profile

    def _cached_profile_is_usable(
        self,
        profile: CompanyProfile,
        request: CompanyResearchRequest,
    ) -> bool:
        """Decide whether a cached profile is complete enough and context-specific enough to reuse."""

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
        if missing_count > 2:
            return False

        product = (request.product_or_solution or "").strip().lower()
        if product:
            profile_text = " ".join(
                [
                    profile.name,
                    profile.specialization,
                    " ".join(profile.products_or_solutions),
                    " ".join(profile.evidence_urls),
                ]
            ).lower()
            product_tokens = [token for token in product.replace("/", " ").split() if len(token) >= 4]
            if product_tokens and not any(token in profile_text for token in product_tokens):
                return False

        return True

    def _merge_profile_with_request(
        self,
        profile: CompanyProfile,
        request: CompanyResearchRequest,
    ) -> CompanyProfile:
        """Merge trusted user-provided hints and extraction context into blank or missing fields."""

        if request.classification and profile.vertical_or_horizontal in {"", "unknown"}:
            profile.vertical_or_horizontal = request.classification

        if request.website and not profile.website:
            profile.website = request.website

        if request.product_or_solution:
            profile.products_or_solutions = unique_preserve_order(
                profile.products_or_solutions + [request.product_or_solution]
            )

        if request.candidate_evidence_urls:
            profile.evidence_urls = unique_preserve_order(
                profile.evidence_urls + request.candidate_evidence_urls
            )

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