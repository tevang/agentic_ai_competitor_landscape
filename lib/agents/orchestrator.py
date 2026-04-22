from lib.models import PipelineStep, CompanyProfile
from lib.llm_utils import LLM
from lib.evidence import EvidenceStore
from lib.agents.researcher import build_query_plan, collect_evidence_for_step, extract_candidates, refine_queries
from lib.agents.enricher import enrich_company
from lib.agents.verifier import verify_company_for_step
from lib.utils import canonical_name
from tavily import TavilyClient

def process_step(
    llm: LLM, 
    tavily_client: TavilyClient, 
    store: EvidenceStore, 
    profile_cache: dict[str, CompanyProfile], 
    step: PipelineStep, 
    search_results_per_query: int = 5
) -> list[dict]:
    """
    Orchestrates the full research, enrichment, and verification process for a single pipeline step.
    """
    print(f"\n>>> PROCESSING STEP: {step.step} ({step.phase})")
    
    # 1. Plan queries
    queries = build_query_plan(llm, step)
    
    # 2. Collect evidence
    docs = collect_evidence_for_step(tavily_client, step, queries, store, search_results_per_query)
    
    # 3. Extract candidates
    candidates = extract_candidates(llm, step, docs)
    print(f"    Found {len(candidates)} initial candidates.")

    # 4. Optional refinement if count is low
    if len(candidates) < 3:
        new_queries = refine_queries(step, candidates)
        more_docs = collect_evidence_for_step(tavily_client, step, new_queries, store, search_results_per_query)
        candidates = extract_candidates(llm, step, docs + more_docs)
        print(f"    After refinement: {len(candidates)} candidates.")

    results = []
    # 5. Profile & Verify each candidate
    for cand in candidates:
        cname_key = canonical_name(cand.name)
        
        # Enrich if not in cache
        if cname_key not in profile_cache:
            try:
                print(f"    Enriching profile: {cand.name}...")
                profile = enrich_company(llm, tavily_client, store, cand.name)
                profile_cache[cname_key] = profile
            except Exception as e:
                print(f"    [warn] Enrichment failed for {cand.name}: {e}")
                continue
        else:
            profile = profile_cache[cname_key]
        
        # Verify for this step
        try:
            print(f"    Verifying {cand.name} for {step.step}...")
            v_res = verify_company_for_step(llm, store, step, profile, cand.rationale)
        except Exception as e:
            print(f"    [warn] Verification failed for {profile.name}: {e}")
            continue
        
        if v_res.belongs:
            results.append({
                "phase": step.phase,
                "step": step.step,
                "company": profile.name,
                "vertical_or_horizontal": profile.vertical_or_horizontal,
                "funding": profile.funding,
                "employees": profile.employees,
                "founded": profile.founded,
                "headquarters": profile.headquarters,
                "presence": "; ".join(profile.presence),
                "specialization": profile.specialization,
                "agentic_posture": profile.explicit_agentic_posture,
                "confidence": round(min(cand.confidence, profile.confidence, v_res.confidence), 2),
                "reason": v_res.reasoning,
            })
        
    print(f"    Kept {len(results)} verified companies.")
    return results
