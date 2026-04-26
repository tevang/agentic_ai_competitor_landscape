"""Verification agent that decides whether a company truly belongs in a step."""

from lib.config import AppConfig
from lib.llm import LLM
from lib.models import CompanyProfile, EvidenceDoc, PipelineStep, TaxonomyAssignment, VerificationResult
from lib.retrieval.evidence_store import EvidenceStore
from lib.utils.text_utils import build_step_signature, evidence_to_context


class VerificationAgent:
    """Verify step-level company inclusion decisions using retrieved evidence."""

    def __init__(self, llm: LLM, config: AppConfig, store: EvidenceStore) -> None:
        """Store the services required for step-specific verification and cache reuse."""

        self.llm = llm
        self.config = config
        self.store = store

    def verify_company_for_step(
        self,
        step: PipelineStep,
        profile: CompanyProfile,
        candidate_rationale: str,
        taxonomy_assignment: TaxonomyAssignment | None = None,
        candidate_evidence_urls: list[str] | None = None,
        candidate_product_or_solution: str = "",
    ) -> VerificationResult:
        """Verify whether a company should be included for a specific pipeline step."""

        step_signature = build_step_signature(step.phase, step.step, step.activities)
        if self.config.search_protocol.reuse_existing_verifications:
            cached = self.store.get_verification(
                phase=step.phase,
                step=step.step,
                step_signature=step_signature,
                company_name=profile.name,
                min_confidence=self.config.search_protocol.skip_llm_if_existing_verification_confidence_at_least,
            )
            if cached is not None:
                return cached

        product_text = candidate_product_or_solution or "; ".join(profile.products_or_solutions)
        direct_url_docs = self._candidate_url_docs(
            urls=(candidate_evidence_urls or []) + profile.evidence_urls,
            company_name=profile.name,
        )
        rag_docs = self.store.query(
            (
                f"{profile.name} {product_text} {step.phase} {step.step} {step.activities} "
                f"AI automation agentic platform product pharmacovigilance safety"
            ),
            n_results=self.config.rag.verification_rag_results,
        )
        context = evidence_to_context(
            direct_url_docs + rag_docs,
            limit=self.config.rag.verification_context_limit,
            chars_per_item=self.config.rag.verification_context_chars_per_item,
        )

        taxonomy_text = "Not provided."
        if self.config.taxonomy.include_in_verification_prompt and taxonomy_assignment is not None:
            taxonomy_text = (
                f"Primary phase bucket: {taxonomy_assignment.primary_phase}\n"
                f"Primary subcategory: {taxonomy_assignment.primary_subcategory}\n"
                f"Allowed phase labels: {', '.join(taxonomy_assignment.phase_labels)}\n"
                f"Allowed subcategories: {', '.join(taxonomy_assignment.subcategory_labels)}"
            )

        prompt = f"""
You are a verification agent.

STEP:
Phase: {step.phase}
Step: {step.step}
Activities: {step.activities}

CONTROLLED TAXONOMY TARGET:
{taxonomy_text}

COMPANY PROFILE:
Name: {profile.name}
Type: {profile.vertical_or_horizontal}
Website: {profile.website or "unknown"}
Products / solutions: {", ".join(profile.products_or_solutions) or "unknown"}
Candidate product / solution: {product_text or "unknown"}
Specialization: {profile.specialization}
Agentic posture: {profile.explicit_agentic_posture}
Existing taxonomy phase labels: {", ".join(profile.taxonomy_phase_labels) or "none"}
Existing taxonomy subcategory labels: {", ".join(profile.taxonomy_subcategory_labels) or "none"}

INITIAL RATIONALE:
{candidate_rationale}

EVIDENCE:
{context}

Decision rule:
Include the company if evidence suggests it directly develops, owns, sells, or materially deploys AI, agentic AI, autonomous workflow software, AI agents, generative AI, machine learning, NLP, cognitive automation, or productized workflow automation relevant to this exact step and controlled taxonomy target.

Important:
- The exact phrase "agentic AI" is not required.
- Incumbent platforms should be included when their evidence shows AI/ML/NLP/GenAI/agentic or substantial workflow automation in this step.
- Product ownership matters: include the owner/vendor of the relevant product, not a publisher writing about that vendor.
- CRO/BPO/SI/service firms should be included only when there is evidence of a named platform, AI-enabled managed service, productized automation layer, or repeatable software capability.
- Exclude article publishers, blogs, market analysts, customer case-study subjects, or implementation partners unless they themselves sell a relevant product or productized service.
- Exclude legacy non-AI systems if evidence shows only ordinary case management, consulting, or generic services.
- Exclude companies that are relevant to a different pipeline step but not this one.

Return JSON:
{{
  "include": true,
  "confidence": 0.0,
  "reason": "one paragraph explaining the evidence basis"
}}
"""
        data = self.llm.ask_json(prompt)
        verdict = VerificationResult(**data)
        self.store.save_verification(
            phase=step.phase,
            step=step.step,
            step_signature=step_signature,
            company_name=profile.name,
            candidate_rationale=candidate_rationale,
            verdict=verdict,
        )
        return verdict

    def _candidate_url_docs(self, urls: list[str], company_name: str) -> list[EvidenceDoc]:
        """Pull cached/fetched candidate evidence URLs directly into verification context."""

        docs: list[EvidenceDoc] = []
        seen_urls: set[str] = set()

        for url in urls[:10]:
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            for record in self.store.get_url_evidence(url=url, limit=2):
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
                        company_name=company_name,
                        source_type=record.get("source_type", "candidate_url"),
                        extraction_status=record.get("extraction_status", ""),
                        blocked_reason=record.get("blocked_reason", ""),
                        render_mode=record.get("render_mode", ""),
                        quality_score=float(record.get("quality_score", 0.0) or 0.0),
                    )
                )

        return docs