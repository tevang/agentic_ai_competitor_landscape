"""Research agent that runs the search-and-fetch stage of the workflow."""

from lib.config import AppConfig
from lib.models import CompanyResearchRequest, EvidenceDoc, PageFetchResult, PipelineStep
from lib.retrieval.evidence_store import EvidenceStore
from lib.retrieval.web_search import WebSearchService
from lib.utils.text_utils import build_step_signature, sha1_hash, unique_preserve_order


class ResearchAgent:
    """Collect evidence from search results, fetched web pages, and cached vector-store records."""

    def __init__(self, config: AppConfig, web_search: WebSearchService, store: EvidenceStore) -> None:
        """Store the services used for search, cache reuse, and evidence persistence."""

        self.config = config
        self.web_search = web_search
        self.store = store

    def collect_step_evidence(self, step: PipelineStep, queries: list[str]) -> list[EvidenceDoc]:
        """Collect evidence for a specific pipeline step, consulting cached records first."""

        step_signature = build_step_signature(step.phase, step.step, step.activities)

        cached_docs = []
        if self.config.search_protocol.reuse_existing_step_evidence:
            cached_docs = self._hydrate_evidence_docs(
                self.store.get_step_evidence(
                    phase=step.phase,
                    step=step.step,
                    step_signature=step_signature,
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
            step_signature=step_signature,
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
            direct_website_doc = self._build_url_doc(
                url=request.website,
                request=request,
                source_type="direct_website",
                query="DIRECT_WEBSITE",
                title=request.company_name,
            )
            if direct_website_doc is not None:
                docs.append(direct_website_doc)

        for evidence_url in request.candidate_evidence_urls[:8]:
            candidate_doc = self._build_url_doc(
                url=evidence_url,
                request=request,
                source_type="candidate_evidence_url",
                query="CANDIDATE_EVIDENCE_URL",
                title=request.company_name,
            )
            if candidate_doc is not None:
                docs.append(candidate_doc)

        new_docs = self._collect_evidence(
            phase=request.phase or "GLOBAL",
            step_name=request.step or "GLOBAL",
            step_signature="",
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
        step_signature: str,
        company_name: str,
        queries: list[str],
        max_results: int,
        fetch_top_n: int,
        preferred_domains: list[str],
    ) -> list[EvidenceDoc]:
        """Execute queries and convert broad plus priority-site results into evidence docs."""

        docs: list[EvidenceDoc] = []
        unique_queries = unique_preserve_order(queries)

        for query in unique_queries:
            docs.extend(
                self._collect_query_results(
                    phase=phase,
                    step_name=step_name,
                    step_signature=step_signature,
                    company_name=company_name,
                    query=query,
                    max_results=max_results,
                    fetch_top_n=fetch_top_n,
                    source_type="web_search",
                )
            )

            if (
                preferred_domains
                and self.config.discovery.priority_domains_as_site_queries
                and not query.strip().lower().startswith("site:")
            ):
                for domain in preferred_domains[: self.config.discovery.priority_site_query_limit]:
                    site_query = f"site:{domain} {query}"
                    docs.extend(
                        self._collect_query_results(
                            phase=phase,
                            step_name=step_name,
                            step_signature=step_signature,
                            company_name=company_name,
                            query=site_query,
                            max_results=self.config.discovery.priority_site_results,
                            fetch_top_n=min(fetch_top_n, self.config.discovery.priority_site_results),
                            source_type="priority_site_search",
                        )
                    )

        deduped_docs = self._dedupe_docs(docs)
        self.store.add_docs(deduped_docs)
        return deduped_docs

    def _collect_query_results(
        self,
        phase: str,
        step_name: str,
        step_signature: str,
        company_name: str,
        query: str,
        max_results: int,
        fetch_top_n: int,
        source_type: str,
    ) -> list[EvidenceDoc]:
        """Run one broad search query and fetch full text for the top-N results."""

        docs: list[EvidenceDoc] = []
        results = self.web_search.search(
            query=query,
            max_results_override=max_results,
        )

        for index, result in enumerate(results):
            url = result.get("url", "")
            if not url:
                continue

            title = result.get("title", "")
            snippet = result.get("content", "") or result.get("snippet", "")
            fetch_result = PageFetchResult(extraction_status="not_fetched")
            if index < fetch_top_n:
                fetch_result = self._get_cached_or_fetch_page(url)

            docs.append(
                EvidenceDoc(
                    phase=phase,
                    step=step_name,
                    activities_signature=step_signature,
                    query=query,
                    url=url,
                    title=title,
                    snippet=snippet,
                    text=fetch_result.text,
                    company_name=company_name,
                    source_type=source_type,
                    extraction_status=fetch_result.extraction_status,
                    blocked_reason=fetch_result.blocked_reason,
                    render_mode=fetch_result.render_mode,
                    quality_score=fetch_result.quality_score,
                )
            )

        return docs

    def _build_url_doc(
        self,
        url: str,
        request: CompanyResearchRequest,
        source_type: str,
        query: str,
        title: str,
    ) -> EvidenceDoc | None:
        """Build a direct evidence document from a URL."""

        fetch_result = self._get_cached_or_fetch_page(url)
        if not fetch_result.text:
            return None

        doc = EvidenceDoc(
            phase=request.phase or "GLOBAL",
            step=request.step or "GLOBAL",
            activities_signature="",
            query=query,
            url=url,
            title=title,
            snippet=request.candidate_rationale,
            text=fetch_result.text,
            company_name=request.company_name,
            source_type=source_type,
            extraction_status=fetch_result.extraction_status,
            blocked_reason=fetch_result.blocked_reason,
            render_mode=fetch_result.render_mode,
            quality_score=fetch_result.quality_score,
        )
        self.store.add_docs([doc])
        return doc

    def _get_cached_or_fetch_page(self, url: str) -> PageFetchResult:
        """Reuse cached page text from the vector store before fetching or rendering the URL again."""

        if self.config.search_protocol.prefer_cached_url_text:
            cached_docs = self.store.get_url_evidence(url=url, limit=1)
            if cached_docs and cached_docs[0].get("text"):
                return PageFetchResult(
                    text=cached_docs[0].get("text", ""),
                    extraction_status=cached_docs[0].get("extraction_status", "cached"),
                    blocked_reason=cached_docs[0].get("blocked_reason", ""),
                    render_mode=cached_docs[0].get("render_mode", "cached"),
                    quality_score=float(cached_docs[0].get("quality_score", 0.0) or 0.0),
                )

        return self.web_search.fetch_page(url)

    def _hydrate_evidence_docs(self, records: list[dict[str, str]]) -> list[EvidenceDoc]:
        """Convert raw vector-store records into EvidenceDoc instances."""

        docs: list[EvidenceDoc] = []
        for record in records:
            try:
                docs.append(
                    EvidenceDoc(
                        phase=record.get("phase", ""),
                        step=record.get("step", ""),
                        activities_signature=record.get("activities_signature", ""),
                        query=record.get("query", ""),
                        url=record.get("url", ""),
                        title=record.get("title", ""),
                        snippet=record.get("snippet", ""),
                        text=record.get("text", ""),
                        company_name=record.get("company_name", ""),
                        source_type=record.get("source_type", "cached"),
                        extraction_status=record.get("extraction_status", "cached"),
                        blocked_reason=record.get("blocked_reason", ""),
                        render_mode=record.get("render_mode", "cached"),
                        quality_score=float(record.get("quality_score", 0.0) or 0.0),
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
            fingerprint = sha1_hash(
                f"{doc.query}|{doc.url}|{doc.text}|{doc.snippet}|{doc.extraction_status}|{doc.render_mode}"
            )
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            deduped.append(doc)

        return deduped