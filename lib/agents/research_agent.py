"""Research agent that runs the search-and-fetch stage of the workflow."""

from lib.config import AppConfig
from lib.models import CompanyResearchRequest, EvidenceDoc, PipelineStep
from lib.retrieval.evidence_store import EvidenceStore
from lib.retrieval.web_search import WebSearchService
from lib.utils.text_utils import sha1_hash


class ResearchAgent:
    """Collect evidence from search results, fetched web pages, and cached vector-store records."""

    def __init__(self, config: AppConfig, web_search: WebSearchService, store: EvidenceStore) -> None:
        """Store the services used for search, cache reuse, and evidence persistence."""

        self.config = config
        self.web_search = web_search
        self.store = store

    def collect_step_evidence(self, step: PipelineStep, queries: list[str]) -> list[EvidenceDoc]:
        """Collect evidence for a specific pipeline step, consulting cached records first."""

        cached_docs = []
        if self.config.search_protocol.reuse_existing_step_evidence:
            cached_docs = self._hydrate_evidence_docs(
                self.store.get_step_evidence(
                    phase=step.phase,
                    step=step.step,
                    limit=self.config.search_protocol.skip_web_if_existing_step_docs_at_least,
                )
            )
            if (
                len(cached_docs) >= self.config.search_protocol.skip_web_if_existing_step_docs_at_least
                and not self.config.search_protocol.allow_web_search_after_cache_hit
            ):
                return cached_docs

        new_docs = self._collect_evidence(
            phase=step.phase,
            step_name=step.step,
            company_name="",
            queries=queries,
            max_results=self.config.get_active_search_profile().step_search_max_results,
            fetch_top_n=self.config.get_active_search_profile().step_fetch_text_for_top_n_results,
            preferred_domains=[],
        )
        return self._dedupe_docs(cached_docs + new_docs)

    def collect_company_evidence(self, request: CompanyResearchRequest) -> list[EvidenceDoc]:
        """Collect evidence used to confirm and enrich a company profile."""

        cached_docs = []
        if self.config.search_protocol.reuse_existing_company_evidence:
            cached_docs = self._hydrate_evidence_docs(
                self.store.get_company_evidence(
                    company_name=request.company_name,
                    limit=self.config.search_protocol.skip_web_if_existing_company_docs_at_least,
                )
            )
            if (
                len(cached_docs) >= self.config.search_protocol.skip_web_if_existing_company_docs_at_least
                and not self.config.search_protocol.allow_web_search_after_cache_hit
            ):
                return cached_docs

        docs = list(cached_docs)

        if request.website:
            direct_website_doc = self._build_direct_website_doc(request)
            if direct_website_doc is not None:
                docs.append(direct_website_doc)

        new_docs = self._collect_evidence(
            phase=request.phase or "GLOBAL",
            step_name=request.step or "GLOBAL",
            company_name=request.company_name,
            queries=request.query_hints,
            max_results=self.config.get_active_search_profile().company_search_max_results,
            fetch_top_n=self.config.get_active_search_profile().company_fetch_text_for_top_n_results,
            preferred_domains=request.preferred_domains,
        )
        return self._dedupe_docs(docs + new_docs)

    def _collect_evidence(
        self,
        phase: str,
        step_name: str,
        company_name: str,
        queries: list[str],
        max_results: int,
        fetch_top_n: int,
        preferred_domains: list[str],
    ) -> list[EvidenceDoc]:
        """Execute a set of queries and convert the results into normalized evidence documents."""

        docs: list[EvidenceDoc] = []

        for query in queries:
            results = self.web_search.search(
                query=query,
                max_results_override=max_results,
                include_domains_override=preferred_domains,
            )
            for index, result in enumerate(results):
                url = result.get("url", "")
                if not url:
                    continue

                title = result.get("title", "")
                snippet = result.get("content", "") or result.get("snippet", "")
                page_text = ""
                if index < fetch_top_n:
                    page_text = self._get_cached_or_fetch_page_text(url)

                docs.append(
                    EvidenceDoc(
                        phase=phase,
                        step=step_name,
                        query=query,
                        url=url,
                        title=title,
                        snippet=snippet,
                        text=page_text,
                        company_name=company_name,
                        source_type="web_search",
                    )
                )

        self.store.add_docs(docs)
        return docs

    def _build_direct_website_doc(self, request: CompanyResearchRequest) -> EvidenceDoc | None:
        """Build a direct evidence document from the company website before search-engine calls."""

        page_text = self._get_cached_or_fetch_page_text(request.website)
        if not page_text:
            return None

        doc = EvidenceDoc(
            phase=request.phase or "GLOBAL",
            step=request.step or "GLOBAL",
            query="DIRECT_WEBSITE",
            url=request.website,
            title=request.company_name,
            snippet="",
            text=page_text,
            company_name=request.company_name,
            source_type="direct_website",
        )
        self.store.add_docs([doc])
        return doc

    def _get_cached_or_fetch_page_text(self, url: str) -> str:
        """Reuse cached page text from the vector store before fetching the URL again."""

        if self.config.search_protocol.prefer_cached_url_text:
            cached_docs = self.store.get_url_evidence(url=url, limit=1)
            if cached_docs and cached_docs[0].get("text"):
                return cached_docs[0]["text"]

        return self.web_search.fetch_page_text(url)

    def _hydrate_evidence_docs(self, records: list[dict[str, str]]) -> list[EvidenceDoc]:
        """Convert raw vector-store records into EvidenceDoc instances."""

        docs: list[EvidenceDoc] = []
        for record in records:
            try:
                docs.append(
                    EvidenceDoc(
                        phase=record.get("phase", ""),
                        step=record.get("step", ""),
                        query=record.get("query", ""),
                        url=record.get("url", ""),
                        title=record.get("title", ""),
                        snippet=record.get("snippet", ""),
                        text=record.get("text", ""),
                        company_name=record.get("company_name", ""),
                        source_type=record.get("source_type", "cached"),
                    )
                )
            except Exception:
                continue
        return docs

    def _dedupe_docs(self, docs: list[EvidenceDoc]) -> list[EvidenceDoc]:
        """Deduplicate evidence documents using query, URL, and content fingerprints."""

        seen: set[str] = set()
        deduped: list[EvidenceDoc] = []

        for doc in docs:
            fingerprint = sha1_hash(f"{doc.query}|{doc.url}|{doc.text}|{doc.snippet}")
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            deduped.append(doc)

        return deduped