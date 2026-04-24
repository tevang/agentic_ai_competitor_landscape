"""Verification agent that decides whether a company truly belongs in a step."""

from lib.config import AppConfig
from lib.llm import LLM
from lib.models import CompanyProfile, PipelineStep, VerificationResult
from lib.retrieval.evidence_store import EvidenceStore
from lib.utils.text_utils import evidence_to_context


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
    ) -> VerificationResult:
        """Verify whether a company should be included for a specific pipeline step."""

        if self.config.search_protocol.reuse_existing_verifications:
            cached = self.store.get_verification(
                phase=step.phase,
                step=step.step,
                company_name=profile.name,
                min_confidence=self.config.search_protocol.skip_llm_if_existing_verification_confidence_at_least,
            )
            if cached is not None:
                return cached

        rag_docs = self.store.query(
            f"{profile.name} {step.phase} {step.step} {step.activities}",
            n_results=self.config.rag.verification_rag_results,
        )
        context = evidence_to_context(
            rag_docs,
            limit=self.config.rag.verification_context_limit,
            chars_per_item=self.config.rag.verification_context_chars_per_item,
        )

        prompt = f"""
You are a verification agent.

STEP:
Phase: {step.phase}
Step: {step.step}
Activities: {step.activities}

COMPANY PROFILE:
Name: {profile.name}
Type: {profile.vertical_or_horizontal}
Website: {profile.website or "unknown"}
Specialization: {profile.specialization}
Agentic posture: {profile.explicit_agentic_posture}

INITIAL RATIONALE:
{candidate_rationale}

EVIDENCE:
{context}

Decision rule:
Include the company only if the evidence suggests it directly develops, sells, or materially deploys AI automation relevant to this exact step.
Do not include merely adjacent companies unless the adjacency is strong and concrete.

Return JSON:
{{
  "include": true,
  "confidence": 0.0,
  "reason": "one paragraph"
}}
"""
        data = self.llm.ask_json(prompt)
        verdict = VerificationResult(**data)
        self.store.save_verification(
            phase=step.phase,
            step=step.step,
            company_name=profile.name,
            candidate_rationale=candidate_rationale,
            verdict=verdict,
        )
        return verdict