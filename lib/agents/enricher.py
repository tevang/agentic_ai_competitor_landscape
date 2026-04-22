from lib.models import CompanyProfile, EvidenceDoc
from lib.llm_utils import LLM, search_web, fetch_page_text
from lib.evidence import EvidenceStore
from lib.utils import evidence_to_context
from tavily import TavilyClient

def enrich_company(llm: LLM, tavily_client: TavilyClient, store: EvidenceStore, company_name: str) -> CompanyProfile:
    """
    Enriches a company profile by searching for more detailed information.
    """
    queries = [
        f'"{company_name}" biotech AI company funding founded headquarters',
        f'site:linkedin.com/company "{company_name}"',
        f'"{company_name}" offices locations about',
        f'"{company_name}" product platform biotech AI',
    ]

    docs: list[EvidenceDoc] = []
    for query in queries:
        results = search_web(tavily_client, query)
        for res in results:
            url = res.get("url", "")
            title = res.get("title", "")
            snippet = res.get("content", "") or res.get("snippet", "")
            page_text = fetch_page_text(url)[:2500]
            docs.append(
                EvidenceDoc(
                    phase="GLOBAL",
                    step="GLOBAL",
                    query=query,
                    url=url,
                    title=title,
                    snippet=snippet,
                    text=page_text,
                )
            )

    store.add_docs(docs)
    rag_docs = store.query(f"{company_name} company funding employees founded headquarters offices specialization", n_results=10)
    
    # Adapt RAG results to EvidenceDoc-like structures for the context builder
    context_docs = docs + [
        EvidenceDoc(
            phase="RAG", 
            step="RAG", 
            query=d.get('metadata', {}).get('query', ''), 
            url=d.get('metadata', {}).get('url', ''), 
            title=d.get('metadata', {}).get('title', ''), 
            snippet='', 
            text=d.get('text', '')
        ) for d in rag_docs
    ]
    
    context = evidence_to_context(context_docs, limit=14, chars_per_item=900)

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
  "funding": "e.g. $50M Series B",
  "employees": "e.g. 51-200",
  "founded": "YYYY",
  "headquarters": "City, Country",
  "presence": ["USA", "Europe"],
  "specialization": "Primary focus area",
  "explicit_agentic_posture": "explicit | adjacent | unclear",
  "confidence": 0.0-1.0,
  "evidence_urls": ["url1", "url2"]
}}
"""
    data = llm.ask_json(prompt)
    try:
        return CompanyProfile(**data)
    except Exception:
        return CompanyProfile(name=company_name, vertical_or_horizontal="unknown")
