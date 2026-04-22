from lib.models import PipelineStep, CompanyProfile, VerificationResult, EvidenceDoc
from lib.llm_utils import LLM
from lib.evidence import EvidenceStore
from lib.utils import evidence_to_context

def verify_company_for_step(llm: LLM, store: EvidenceStore, step: PipelineStep, profile: CompanyProfile, candidate_rationale: str) -> VerificationResult:
    """
    Verifies if a company truly belongs in a specific pipeline step based on evidence.
    """
    # Retrieve relevant snippets from the store for this specific company + step
    rag_docs = store.query(f"{profile.name} {step.step} {step.activities}", n_results=10)
    
    # Adapt RAG results for the context builder
    context_docs = [
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
    
    context = evidence_to_context(context_docs, limit=10, chars_per_item=1000)

    prompt = f"""
You are a verification agent. Determine if the company truly offers a solution for the specific pipeline step.

COMPANY: {profile.name}
SPECIALIZATION: {profile.specialization}
PIPELINE STEP: {step.step}
STEP DESCRIPTION: {step.activities}
INITIAL RATIONALE: {candidate_rationale}

EVIDENCE FROM WEB:
{context}

Rules:
- A company "belongs" if they have a product, service, or documented capability for THIS EXACT STEP.
- If they are only adjacent (e.g., they provide the lab equipment but not the AI for target validation), mark as false.

Output JSON:
{{
  "belongs": true | false,
  "confidence": 0.0-1.0,
  "reasoning": "Explain your decision in one sentence"
}}
"""
    data = llm.ask_json(prompt)
    try:
        return VerificationResult(**data)
    except Exception:
        return VerificationResult(belongs=False, confidence=0.0, reasoning="Error parsing verification")
