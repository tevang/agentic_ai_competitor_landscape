"""Research agent that runs the search-and-fetch stage of the workflow."""

from lib.config import AppConfig
from lib.models import EvidenceDoc, PipelineStep
from lib.retrieval.evidence_store import EvidenceStore
from lib.retrieval.web_search import WebSearchService


class ResearchAgent:
    """Collect evidence from search results and fetched web pages."""

    def __init__(self, config: AppConfig, web_search: WebSearchService, store: EvidenceStore) -> None:
        """Store the services used for search and evidence persistence."""

        self.config = config
        self.web_search = web_search
        self.store = store

    def collect_step_evidence(self, step: PipelineStep, queries: list[str]) -> list[EvidenceDoc]:
        """Collect evidence for a specific pipeline step from the configured search pass."""

        return self._collect_evidence(
            phase=step.phase,
            step_name=step.step,
            queries=queries,
            max_results=self.config.tavily.step_search_max_results,
            fetch_top_n=self.config.tavily.step_fetch_text_for_top_n_results,
        )

    def collect_company_evidence(self, company_name: str, queries: list[str]) -> list[EvidenceDoc]:
        """Collect evidence used to enrich a company profile across multiple sources."""

        return self._collect_evidence(
            phase="GLOBAL",
            step_name="GLOBAL",
            queries=queries,
            max_results=self.config.tavily.company_search_max_results,
            fetch_top_n=self.config.tavily.company_fetch_text_for_top_n_results,
        )

    def _collect_evidence(
        self,
        phase: str,
        step_name: str,
        queries: list[str],
        max_results: int,
        fetch_top_n: int,
    ) -> list[EvidenceDoc]:
        """Execute a set of queries and convert the results into normalized evidence documents."""

        docs: list[EvidenceDoc] = []

        for query in queries:
            results = self.web_search.search(query, max_results_override=max_results)
            for index, result in enumerate(results):
                url = result.get("url", "")
                if not url:
                    continue

                title = result.get("title", "")
                snippet = result.get("content", "") or result.get("snippet", "")
                page_text = self.web_search.fetch_page_text(url) if index < fetch_top_n else ""

                docs.append(
                    EvidenceDoc(
                        phase=phase,
                        step=step_name,
                        query=query,
                        url=url,
                        title=title,
                        snippet=snippet,
                        text=page_text,
                    )
                )

        self.store.add_docs(docs)
        return docs