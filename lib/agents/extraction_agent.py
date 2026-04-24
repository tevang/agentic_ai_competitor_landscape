"""Extraction agent that identifies candidate competitors from collected evidence."""

from lib.config import AppConfig
from lib.llm import LLM
from lib.models import Candidate, EvidenceDoc, PipelineStep
from lib.retrieval.evidence_store import EvidenceStore
from lib.utils.text_utils import evidence_to_context, fuzzy_dedupe_candidates


class ExtractionAgent:
    """Extract and deduplicate candidate companies for a single pipeline step."""

    def __init__(self, llm: LLM, config: AppConfig, store: EvidenceStore) -> None:
        """Store the dependencies used for candidate extraction and cache reuse."""

        self.llm = llm
        self.config = config
        self.store = store

    def extract_candidates(
        self,
        step: PipelineStep,
        docs: list[EvidenceDoc],
        seed_candidates: list[Candidate] | None = None,
    ) -> list[Candidate]:
        """Extract candidate competitors from step-level evidence documents and user seed hints."""

        seed_candidates = seed_candidates or []

        cached_candidates: list[Candidate] = []
        if self.config.search_protocol.reuse_existing_candidates:
            cached_candidates = self.store.get_candidates(step.phase, step.step)

        if cached_candidates:
            merged_candidates = fuzzy_dedupe_candidates(
                cached_candidates + seed_candidates,
                threshold=self.config.dedupe.fuzzy_threshold,
            )
            self.store.save_candidates(step.phase, step.step, merged_candidates)
            return merged_candidates

        context = evidence_to_context(
            docs,
            limit=self.config.rag.step_context_limit,
            chars_per_item=self.config.rag.step_context_chars_per_item,
        )

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
        data = self.llm.ask_json(prompt)
        candidates: list[Candidate] = []
        for item in data.get("candidates", []):
            try:
                candidates.append(Candidate(**item))
            except Exception:
                continue

        merged_candidates = fuzzy_dedupe_candidates(
            candidates + seed_candidates,
            threshold=self.config.dedupe.fuzzy_threshold,
        )
        self.store.save_candidates(step.phase, step.step, merged_candidates)
        return merged_candidates