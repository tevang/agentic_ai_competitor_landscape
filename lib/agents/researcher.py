from lib.models import PipelineStep, EvidenceDoc, Candidate
from lib.llm_utils import LLM, search_web, fetch_page_text
from lib.evidence import EvidenceStore
from lib.utils import fuzzy_dedupe_candidates
from tavily import TavilyClient

def build_query_plan(llm: LLM, step: PipelineStep) -> list[str]:
    """
    Generates a list of targeted search queries for a given pipeline step.
    """

    prompt = f"""
You are a search-planning agent for biotech competitive intelligence.

STEP:
Phase: {step.phase}
Step: {step.step}
Activities: {step.activities}

Task:
Generate 5 web search queries to find companies that build, market, or materially deploy AI or agentic solutions relevant to this exact step.

Requirements:
- Include one query using "agentic AI" or "AI scientist" language.
- Include one query using broader "AI platform" or "machine learning" language.
- Include one query aimed at startup/vendor discovery.
- Include one query aimed at product pages / solution pages.
- Focus on biotech / pharma / drug discovery / clinical / regulatory relevance.

Return JSON:
{{
  "queries": ["...", "...", "...", "...", "..."]
}}
"""
    data = llm.ask_json(prompt)
    queries = data.get("queries", [])
    return [q.strip() for q in queries if q.strip()][:5]


def collect_evidence_for_step(tavily_client: TavilyClient, step: PipelineStep, queries: list[str], store: EvidenceStore, search_results_per_query: int = 5) -> list[EvidenceDoc]:
    """
    Executes search queries and collects evidence documents for a pipeline step.
    """
    docs = []
    for query in queries:
        results = search_web(tavily_client, query, max_results=search_results_per_query)
        for res in results:
            url = res.get("url", "")
            title = res.get("title", "")
            snippet = res.get("content", "") or res.get("snippet", "")
            # Fetch full text for a subset of results to save time/tokens
            page_text = fetch_page_text(url)[:3000]
            docs.append(EvidenceDoc(
                phase=step.phase,
                step=step.step,
                query=query,
                url=url,
                title=title,
                snippet=snippet,
                text=page_text
            ))
    store.add_docs(docs)
    return docs


def extract_candidates(llm: LLM, step: PipelineStep, docs: list[EvidenceDoc]) -> list[Candidate]:
    """
    Extracts candidate companies from the collected evidence documents.
    """
    from lib.utils import evidence_to_context
    context = evidence_to_context(docs, limit=10)
    prompt = f"""
You are an evidence extraction agent.

STEP:
Phase: {step.phase}
Step: {step.step}
Activities: {step.activities}

Definition of relevant competitor:
A company that develops, sells, or materially deploys AI / agentic / autonomous workflow software relevant to this step in drug discovery, preclinical development, clinical development, regulatory review, or post-market work.

Exclude:
- generic CROs unless AI automation is core to the offering
- pure service firms with no product/platform signal
- companies only loosely adjacent to the step

EVIDENCE:
{context}

Return JSON:
{{
  "candidates": [
    {{
      "name": "Company Name",
      "rationale": "Why it is relevant to this step",
      "vertical_or_horizontal_guess": "vertical|horizontal|unclear",
      "confidence": 0.0,
      "evidence_urls": ["url1", "url2"]
    }}
  ]
}}
"""
    data = llm.ask_json(prompt)
    out = []
    for item in data.get("candidates", []):
        try:
            out.append(Candidate(**item))
        except Exception:
            continue
    return fuzzy_dedupe_candidates(out)


def refine_queries(step: PipelineStep, candidates: list[Candidate]) -> list[str]:
    """
    Cheap ReAct-style refinement. If the first pass is weak, broaden slightly.
    """
    seen = ", ".join([c.name for c in candidates[:5]]) or "none"
    return [
        f'"{step.step}" biotech AI startup',
        f'"{step.step}" pharma AI platform company',
        f'"{step.phase}" "{step.step}" machine learning vendor',
        f'"{step.step}" "drug development" "AI" company',
        f'"{step.step}" "agentic AI" pharma {seen}',
    ]
