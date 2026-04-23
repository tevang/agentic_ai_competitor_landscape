"""Enrichment agent that builds normalized company profiles from evidence."""

from lib.config import AppConfig
from lib.llm import LLM
from lib.models import CompanyProfile, EvidenceDoc
from lib.retrieval.evidence_store import EvidenceStore
from lib.utils.text_utils import evidence_to_context
from lib.agents.research_agent import ResearchAgent


class EnrichmentAgent:
    """Enrich company candidates with profile-level metadata and positioning."""

    def __init__(
        self,
        llm: LLM,
        config: AppConfig,
        research_agent: ResearchAgent,
        store: EvidenceStore,
    ) -> None:
        """Store the services needed to enrich a company profile."""

        self.llm = llm
        self.config = config
        self.research_agent = research_agent
        self.store = store

    def enrich_company(self, company_name: str) -> CompanyProfile:
        """Collect evidence for a company and convert it into a normalized profile."""

        queries = self._build_company_queries(company_name)
        docs = self.research_agent.collect_company_evidence(company_name, queries)
        rag_docs = self.store.query(
            f"{company_name} company funding employees founded headquarters offices specialization",
            n_results=self.config.rag.enrichment_rag_results,
        )

        context_items = docs + [
            EvidenceDoc(
                phase="RAG",
                step="RAG",
                query=document.get("query", ""),
                url=document.get("url", ""),
                title=document.get("title", ""),
                snippet="",
                text=document.get("text", ""),
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
{company_name}

Definitions:
- vertical = built specifically for drug R&D / pharma / life-sciences workflows
- horizontal = broader scientific-agent, lab-automation, or research platform spanning multiple domains

Rules:
- Prefer "unknown" to guessing.
- Employees can be an official count or a public range like "201-500".
- Funding can be a round amount or total disclosed funding.
- Presence should list offices / operating hubs / notable geographic footprint.

EVIDENCE:
{context}

Return JSON:
{{
  "name": "{company_name}",
  "vertical_or_horizontal": "vertical|horizontal|unknown",
  "funding": "string",
  "employees": "string",
  "founded": "string",
  "headquarters": "string",
  "presence": ["string"],
  "specialization": "short description",
  "explicit_agentic_posture": "explicit|adjacent|unclear",
  "confidence": 0.0,
  "evidence_urls": ["url1", "url2"]
}}
"""
        data = self.llm.ask_json(prompt)
        return CompanyProfile(**data)

    def _build_company_queries(self, company_name: str) -> list[str]:
        """Construct the company-enrichment search queries for one company."""

        return [
            f'"{company_name}" biotech AI company funding founded headquarters',
            f'site:linkedin.com/company "{company_name}"',
            f'"{company_name}" offices locations about',
            f'"{company_name}" product platform biotech AI',
        ]