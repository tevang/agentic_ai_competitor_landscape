"""Extraction agent that identifies candidate competitors from collected evidence."""

from lib.config import AppConfig
from lib.llm import LLM
from lib.models import Candidate, EvidenceDoc, PipelineStep
from lib.retrieval.evidence_store import EvidenceStore
from lib.taxonomy.schema import format_taxonomy_target_for_step
from lib.utils.text_utils import (
    build_step_signature,
    chunked,
    evidence_to_context,
    fuzzy_dedupe_candidates,
    rank_evidence_docs_for_extraction,
)


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
        """Extract candidate competitors from evidence, merging cached rosters as priors."""

        seed_candidates = seed_candidates or []
        step_signature = build_step_signature(step.phase, step.step, step.activities)

        cached_candidates: list[Candidate] = []
        if self.config.search_protocol.reuse_existing_candidates:
            cached_candidates = self.store.get_candidates(
                step.phase,
                step.step,
                step_signature,
                allow_signature_mismatch=self.config.search_protocol.reuse_rosters_across_activity_text_changes,
            )

        cached_priors = (
            cached_candidates
            if self.config.discovery.include_cached_rosters_as_priors
            else []
        )

        if not docs:
            merged_from_cache = fuzzy_dedupe_candidates(
                self._filter_candidates(cached_priors + seed_candidates),
                threshold=self.config.dedupe.fuzzy_threshold,
            )
            if merged_from_cache:
                self.store.save_candidates(step.phase, step.step, step_signature, merged_from_cache)
            return merged_from_cache

        ranked_docs = rank_evidence_docs_for_extraction(docs)
        batch_size = self.config.discovery.extraction_context_docs_per_batch
        max_docs = batch_size * self.config.discovery.max_extraction_batches
        evidence_batches = chunked(ranked_docs[:max_docs], batch_size)

        extracted_candidates: list[Candidate] = []
        for batch in evidence_batches:
            extracted_candidates.extend(self._extract_from_batch(step, batch))

        merged_candidates = fuzzy_dedupe_candidates(
            self._filter_candidates(cached_priors + extracted_candidates + seed_candidates),
            threshold=self.config.dedupe.fuzzy_threshold,
        )

        self.store.save_candidates(step.phase, step.step, step_signature, merged_candidates)

        if self.config.runtime.verbosity >= 1:
            print(
                "[extract] "
                f"{step.phase} -> {step.step}: "
                f"docs={len(docs)}, "
                f"batches={len(evidence_batches)}, "
                f"cached_priors={len(cached_priors)}, "
                f"candidates={len(merged_candidates)}"
            )

        return merged_candidates

    def _extract_from_batch(self, step: PipelineStep, docs: list[EvidenceDoc]) -> list[Candidate]:
        """Extract candidates from one evidence batch."""

        context = evidence_to_context(
            docs,
            limit=self.config.rag.step_context_limit,
            chars_per_item=self.config.rag.step_context_chars_per_item,
        )
        taxonomy_target = format_taxonomy_target_for_step(step.phase, step.step)
        max_candidates = self.config.discovery.max_candidates_per_extraction_batch
        scan_mode = self.config.runtime.analysis_mode == "landscape_scan"

        prompt = f"""
You are an evidence extraction agent.

STEP:
Phase: {step.phase}
Step: {step.step}
Activities: {step.activities}

CONTROLLED TAXONOMY TARGET:
{taxonomy_target}

Definition of relevant competitor:
A company that develops, owns, sells, or materially deploys AI, agentic AI, autonomous workflow software, AI agents, generative AI, machine learning, NLP, cognitive automation, or productized workflow automation relevant to this exact pipeline step.

Critical source-vs-subject rule:
- Extract the company that owns the relevant product or platform, not merely the publisher of an article.
- If an article is written by Company A but is about Company B's product, Company B is the candidate and Company A is only a source/publisher.
- If a page says it is independent editorial content about a named vendor/product, do not treat the article publisher as the competitor unless the page also proves the publisher sells its own relevant product.
- Product names are not enough by themselves. Return the owning company/vendor in "name" or "owning_company_name", and put the product in "product_or_solution".
- Example pattern: an article about Veeva AI Agents or Veeva Vault Safety should produce "Veeva Systems" as the company and "Veeva Vault Safety / Veeva AI for Safety" as the product, not the article publisher.

Important inclusion rules:
- Include incumbent enterprise platforms when the evidence links them to AI, ML, NLP, GenAI, agents, cognitive automation, or substantial automation for this step.
- Include AI-native startups.
- Include CRO/BPO/SI/service firms only when the evidence points to a productized platform, named automation solution, AI-enabled managed service, or repeatable software layer.
- Do not require the exact phrase "agentic AI"; AI agents, copilots, autonomous workflows, GenAI case processing, ML/NLP extraction, auto-coding, signal automation, or comparable capabilities can qualify.
- Prefer a broad candidate roster over a single obvious company.
- Do not list generic consultancies or service firms unless the evidence ties them to step-specific AI/software capability.
- Do not list companies only loosely adjacent to the controlled taxonomy target.

LANDSCAPE_SCAN_MODE:
{scan_mode}

If LANDSCAPE_SCAN_MODE is true:
- Return only candidate companies/products that can plausibly be mapped from snippets/search results without deep enrichment.
- Prefer official company/product websites when visible.
- Set "website" to the official company or product website when the evidence supports it, otherwise blank.
- Set "explicit_agentic_posture" to:
  - "explicit" when the evidence mentions AI agents, agentic AI, autonomous workflows, GenAI agents, copilots, or comparable agentic posture
  - "adjacent" when the evidence mentions AI, ML, NLP, GenAI, cognitive automation, or workflow automation but not agentic/autonomous language
  - "unclear" when the evidence does not support AI/automation
- Do not invent funding, headcount, founding year, headquarters, or other deep-profile facts.

EVIDENCE:
{context}

Return JSON:
{{
  "candidates": [
    {{
      "name": "Owning Company Name",
      "owning_company_name": "Owning Company Name if clearer than name, otherwise blank",
      "product_or_solution": "Named product, suite, module, or service, if any",
      "website": "official website URL if supported, otherwise blank",
      "explicit_agentic_posture": "explicit|adjacent|unclear",
      "evidence_role": "target_vendor|publisher_only|customer|partner|unclear",
      "rationale": "Why the owning company is relevant to this step, citing the evidence in words",
      "vertical_or_horizontal_guess": "vertical|horizontal|unclear",
      "confidence": 0.0,
      "evidence_urls": ["url1", "url2"]
    }}
  ]
}}

Return at most {max_candidates} candidates from this evidence batch.
"""
        try:
            data = self.llm.ask_json(prompt)
        except Exception:
            return []

        candidates: list[Candidate] = []
        for item in data.get("candidates", [])[:max_candidates]:
            try:
                candidate = Candidate(**item)
                if candidate.owning_company_name and candidate.name != candidate.owning_company_name:
                    candidate.name = candidate.owning_company_name
                candidates.append(candidate)
            except Exception:
                continue

        return candidates

    def _filter_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        """Remove publisher-only entries and apply landscape-scan posture filtering."""

        output: list[Candidate] = []
        allowed_postures = {
            value.strip().lower()
            for value in self.config.discovery.landscape_scan_agentic_postures
            if value.strip()
        }

        for candidate in candidates:
            role = (candidate.evidence_role or "").strip().lower()
            if role == "publisher_only" and candidate.source not in {"user_seed", "user_seed_global_overlap"}:
                continue

            if self.config.runtime.analysis_mode == "landscape_scan":
                posture = (candidate.explicit_agentic_posture or "unclear").strip().lower()
                if allowed_postures and posture not in allowed_postures:
                    continue

            output.append(candidate)

        return output